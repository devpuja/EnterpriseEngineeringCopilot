from pathlib import Path
import os
import stat

import pytest

from app.repository.exceptions import WorkspaceError
from app.repository.workspace_manager import WorkspaceManager
from app.repository.workspace_manager import retry_readonly_removal


def test_unique_workspaces_and_cleanup(tmp_path):
    manager = WorkspaceManager(tmp_path / "workspaces", retention_seconds=3600)
    first = manager.create_workspace()
    second = manager.create_workspace()
    assert first != second
    assert manager.cleanup_workspace(first)
    assert not first.exists()
    assert second.exists()
    assert manager.cleanup_workspace(first)


def test_cleanup_refuses_path_outside_root(tmp_path):
    manager = WorkspaceManager(tmp_path / "workspaces")
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(WorkspaceError):
        manager.cleanup_workspace(outside)


def test_cleanup_rejects_symlinked_workspace(tmp_path):
    manager = WorkspaceManager(tmp_path / "workspaces")
    workspace = manager.create_workspace()
    sibling = tmp_path / "sibling"
    sibling.mkdir()
    workspace.rmdir()
    try:
        workspace.symlink_to(sibling, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Symlinks are unavailable in this test environment: {exc}")

    with pytest.raises(WorkspaceError):
        manager.cleanup_workspace(workspace)
    assert sibling.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows read-only deletion semantics")
def test_cleanup_removes_readonly_git_files(tmp_path):
    manager = WorkspaceManager(tmp_path / "workspaces")
    workspace = manager.create_workspace()
    git_objects = workspace / "repository" / ".git" / "objects"
    git_objects.mkdir(parents=True)
    packed = git_objects / "pack"
    packed.write_bytes(b"git data")
    packed.chmod(stat.S_IREAD)
    assert manager.cleanup_workspace(workspace)
    assert not list(manager.workspace_root.iterdir())


def test_readonly_retry_does_not_hide_unrelated_errors(tmp_path):
    file = tmp_path / "writable"
    file.write_text("data", encoding="utf-8")
    error = PermissionError("unrelated access denial")
    with pytest.raises(PermissionError, match="unrelated access denial"):
        retry_readonly_removal(os.unlink, str(file), (PermissionError, error, None))
    assert file.exists()
