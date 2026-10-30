import pytest

from app.repository.adapters.local_repository import LocalRepositoryAdapter
from app.repository.exceptions import InvalidRepositorySourceError, RepositorySecurityError
from app.repository.workspace_manager import WorkspaceManager


@pytest.mark.asyncio
async def test_valid_local_directory(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "app.py").write_text("print('ok')", encoding="utf-8")
    adapter = LocalRepositoryAdapter(
        workspace_manager=WorkspaceManager(tmp_path / "workspaces"),
        allowed_roots=[str(tmp_path)],
    )
    snapshot = await adapter.retrieve(str(source))
    assert snapshot.source_type == "local"
    assert snapshot.total_files == 1


@pytest.mark.asyncio
async def test_missing_directory(tmp_path):
    adapter = LocalRepositoryAdapter(allowed_roots=[str(tmp_path)])
    with pytest.raises(InvalidRepositorySourceError):
        await adapter.retrieve(str(tmp_path / "missing"))


@pytest.mark.asyncio
async def test_no_allowed_roots_fails_closed(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    adapter = LocalRepositoryAdapter(
        workspace_manager=WorkspaceManager(tmp_path / "workspaces"),
        allowed_roots=[],
    )
    with pytest.raises(RepositorySecurityError):
        await adapter.retrieve(str(source))


@pytest.mark.asyncio
async def test_directory_outside_allowed_roots_is_rejected(tmp_path):
    source = tmp_path / "outside"
    source.mkdir()
    adapter = LocalRepositoryAdapter(
        workspace_manager=WorkspaceManager(tmp_path / "workspaces"),
        allowed_roots=[str(tmp_path / "allowed")],
    )
    with pytest.raises(RepositorySecurityError):
        await adapter.retrieve(str(source))
