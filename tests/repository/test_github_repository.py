import pytest
import subprocess
from pathlib import Path

from app.repository.adapters.github_repository import GitHubRepositoryAdapter
from app.repository.exceptions import InvalidRepositorySourceError
from app.repository.exceptions import RepositorySecurityError
from app.repository.exceptions import RepositoryNotFoundError
from app.repository.analysis.content_access import SnapshotContentReader
from app.repository.workspace_manager import WorkspaceManager


@pytest.mark.parametrize("url", [
    "https://github.com/devpuja/Agents",
    "https://github.com/devpuja/Agents.git",
])
def test_valid_github_urls(url):
    adapter = GitHubRepositoryAdapter()
    owner, repository, normalized_url = adapter.parse_url(url)
    assert owner == "devpuja"
    assert repository == "Agents"
    assert normalized_url == "https://github.com/devpuja/Agents.git"


@pytest.mark.parametrize("url", [
    "http://github.com/devpuja/Agents.git",
    "https://gitlab.com/devpuja/Agents.git",
    "https://github.com/devpuja",
    "https://github.com/devpuja/Agents/tree/main",
    "https://github.com/devpuja/Agents/",
    "https://github.com//Agents.git",
    "https://github.com/dev puja/Agents.git",
])
def test_invalid_github_urls(url):
    adapter = GitHubRepositoryAdapter()
    with pytest.raises(InvalidRepositorySourceError):
        adapter.parse_url(url)


def test_credentials_are_rejected():
    adapter = GitHubRepositoryAdapter()
    with pytest.raises(RepositorySecurityError):
        adapter.parse_url("https://user:token@github.com/devpuja/Agents.git")


@pytest.mark.parametrize("url", [
    "https://github.com.evil.example/devpuja/Agents.git",
    "https://127.0.0.1/devpuja/Agents.git",
    "https://localhost/devpuja/Agents.git",
    "https://github.com:8443/devpuja/Agents.git",
])
def test_ssrf_and_arbitrary_hosts_are_rejected(url):
    adapter = GitHubRepositoryAdapter()
    with pytest.raises((InvalidRepositorySourceError, RepositorySecurityError)):
        adapter.parse_url(url)


@pytest.mark.asyncio
async def test_mocked_clone_captures_commit_and_snapshot(tmp_path, monkeypatch):
    adapter = GitHubRepositoryAdapter(
        workspace_manager=WorkspaceManager(tmp_path / "workspaces")
    )
    def fake_git(args, cwd=None):
        if args[0:2] == ["-c", "core.hooksPath=/dev/null"]:
            destination = Path(args[-1])
            destination.mkdir(parents=True)
            (destination / "app.py").write_text("print('ok')", encoding="utf-8")
        return subprocess.CompletedProcess(args, 0, stdout="a" * 40 + "\n")
    monkeypatch.setattr(adapter, "_git", fake_git)

    snapshot = await adapter.retrieve(
        "https://github.com/devpuja/Agents.git",
        branch="main",
    )
    assert snapshot.source_type == "github"
    assert snapshot.repository_name == "Agents"
    assert snapshot.commit_sha == "a" * 40
    assert snapshot.total_files == 1


@pytest.mark.parametrize("url", [
    "https://github.com/devpuja/Agents/tree/main/agent-project/../other",
    "https://github.com/devpuja/Agents/tree/main/agent-project//nested",
    "https://github.com/devpuja/Agents/tree/main/C:/outside",
    "https://github.com/devpuja/Agents/tree/main/CON",
    "https://github.com/devpuja/Agents/tree/main/agent-project.",
    "https://github.com/devpuja/Agents/tree/main/%2e%2e/other",
    "https://github.com/devpuja/Agents/tree/main/agent-project?token=value",
])
def test_invalid_subdirectory_urls(url):
    with pytest.raises(InvalidRepositorySourceError):
        GitHubRepositoryAdapter().parse_url(url)


@pytest.mark.asyncio
@pytest.mark.parametrize("branch", [None, "main"])
async def test_tree_url_isolates_subdirectory_and_content_reader(tmp_path, monkeypatch, branch):
    manager = WorkspaceManager(tmp_path / "workspaces")
    adapter = GitHubRepositoryAdapter(manager)
    commands = []

    def fake_git(args, cwd=None):
        commands.append(args)
        if "clone" in args:
            destination = Path(args[-1])
            selected = destination / "agent-project" / "nested"
            selected.mkdir(parents=True)
            (selected / "app.py").write_text("print('selected')", encoding="utf-8")
            (destination / "outside.py").write_text("print('outside')", encoding="utf-8")
        return subprocess.CompletedProcess(args, 0, stdout="a" * 40 + "\n")

    monkeypatch.setattr(adapter, "_git", fake_git)
    url = "https://github.com/devpuja/Agents/tree/main/agent-project"
    snapshot = await adapter.retrieve(url, branch=branch)
    assert snapshot.branch == "main"
    assert snapshot.source_reference == url
    assert [item.relative_path for item in snapshot.files] == ["nested/app.py"]
    assert SnapshotContentReader(manager).read_text(snapshot, snapshot.files[0]) == "print('selected')"
    assert commands[0][-3:] == ["main", "https://github.com/devpuja/Agents.git", str(
        manager.workspace_root / str(snapshot.workspace_id) / "repository"
    )]
    assert manager.cleanup_workspace(snapshot.workspace_id)


@pytest.mark.asyncio
async def test_tree_branch_conflict_fails_before_clone(tmp_path, monkeypatch):
    manager = WorkspaceManager(tmp_path / "workspaces")
    adapter = GitHubRepositoryAdapter(manager)
    monkeypatch.setattr(adapter, "_git", lambda *args: pytest.fail("Must not clone"))
    with pytest.raises(InvalidRepositorySourceError, match="conflicts"):
        await adapter.retrieve(
            "https://github.com/devpuja/Agents/tree/main/agent-project", branch="other"
        )
    assert not list(manager.workspace_root.iterdir())


@pytest.mark.asyncio
async def test_missing_subdirectory_cleans_workspace(tmp_path, monkeypatch):
    manager = WorkspaceManager(tmp_path / "workspaces")
    adapter = GitHubRepositoryAdapter(manager)

    def fake_git(args, cwd=None):
        if "clone" in args:
            Path(args[-1]).mkdir(parents=True)
        return subprocess.CompletedProcess(args, 0, stdout="a" * 40 + "\n")

    monkeypatch.setattr(adapter, "_git", fake_git)
    with pytest.raises(RepositoryNotFoundError, match="subdirectory"):
        await adapter.retrieve("https://github.com/devpuja/Agents/tree/main/missing")
    assert not list(manager.workspace_root.iterdir())
