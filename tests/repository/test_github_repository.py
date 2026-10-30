import pytest
import subprocess
from pathlib import Path

from app.repository.adapters.github_repository import GitHubRepositoryAdapter
from app.repository.exceptions import InvalidRepositorySourceError
from app.repository.exceptions import RepositorySecurityError
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
