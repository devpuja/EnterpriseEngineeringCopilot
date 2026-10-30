import pytest

from app.repository.models import RepositoryFile, RepositorySnapshot
from app.repository.workspace_manager import WorkspaceManager
from app.repository.analysis.content_access import SnapshotContentReader


def test_missing_snapshot_workspace_is_rejected(tmp_path):
    manager = WorkspaceManager(tmp_path / "workspaces")
    from uuid import uuid4
    snapshot = RepositorySnapshot(
        source_type="local",
        repository_name="sample",
        source_reference="sample",
        workspace_id=uuid4(),
        files=[],
        total_files=0,
        total_size_bytes=0,
    )
    with pytest.raises(Exception):
        SnapshotContentReader(manager).repository_root(snapshot)


def test_relative_file_content_is_not_absolute_in_result(tmp_path):
    file = RepositoryFile(relative_path="src/app.py", file_name="app.py", extension=".py", size_bytes=6)
    assert file.relative_path == "src/app.py"
