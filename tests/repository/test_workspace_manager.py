from pathlib import Path

import pytest

from app.repository.exceptions import WorkspaceError
from app.repository.workspace_manager import WorkspaceManager


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
