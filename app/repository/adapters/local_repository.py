import asyncio
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from app.config.settings import settings
from app.repository.adapters.base import BaseRepositoryAdapter
from app.repository.exceptions import (
    InvalidRepositorySourceError,
    RepositorySecurityError,
    RepositoryLimitExceededError,
)
from app.repository.file_discovery import FileDiscovery
from app.repository.exclusions import RepositoryExclusions
from app.repository.models import RepositorySnapshot
from app.repository.workspace_manager import WorkspaceManager


class LocalRepositoryAdapter(BaseRepositoryAdapter):
    def __init__(self, workspace_manager: WorkspaceManager | None = None, allowed_roots: list[str] | None = None):
        self.workspace_manager = workspace_manager or WorkspaceManager()
        self.allowed_roots = allowed_roots if allowed_roots is not None else settings.allowed_local_repository_roots

    def _validate_directory(self, source_reference: str) -> Path:
        source = self._safe_resolved_path(source_reference)
        if not source.is_dir():
            raise InvalidRepositorySourceError("Repository source must be a directory.")
        if not self.allowed_roots:
            raise RepositorySecurityError("No allowed local repository roots are configured.")
        roots = [Path(root).expanduser().resolve(strict=False) for root in self.allowed_roots]
        if not any(source == root or root in source.parents for root in roots):
            raise RepositorySecurityError("Repository path is outside permitted local roots.")
        return source

    def _copy_repository(self, source: Path, destination: Path) -> None:
        exclusions = RepositoryExclusions()
        copied_files = 0
        copied_size = 0
        destination.mkdir(parents=True, exist_ok=True)

        for current_root, directories, filenames in os.walk(source, topdown=True, followlinks=False):
            current = Path(current_root)
            relative_current = current.relative_to(source)
            depth = 0 if str(relative_current) == "." else len(relative_current.parts)
            if depth > settings.maximum_directory_traversal_depth:
                directories[:] = []
                continue

            for name in list(directories):
                if (current / name).is_symlink():
                    raise RepositorySecurityError("Symlinks are not allowed in repository snapshots.")
            directories[:] = [
                name for name in directories
                if not exclusions.is_excluded_directory(name)
            ]

            target_current = destination / relative_current
            target_current.mkdir(parents=True, exist_ok=True)
            for filename in filenames:
                source_file = current / filename
                relative = source_file.relative_to(source)
                if exclusions.is_excluded(relative.as_posix()):
                    continue
                if source_file.is_symlink():
                    raise RepositorySecurityError("Symlinks are not allowed in repository snapshots.")
                try:
                    stat = source_file.stat()
                    if not source_file.is_file():
                        continue
                    if stat.st_size > settings.maximum_repository_file_size_bytes:
                        raise RepositoryLimitExceededError("Repository individual file size limit exceeded.")
                    copied_size += stat.st_size
                    copied_files += 1
                    if copied_size > settings.maximum_repository_size_bytes:
                        raise RepositoryLimitExceededError("Repository size limit exceeded.")
                    if copied_files > settings.maximum_repository_file_count:
                        raise RepositoryLimitExceededError("Repository file count limit exceeded.")
                    target_file = destination / relative
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_file, target_file, follow_symlinks=False)
                except RepositoryLimitExceededError:
                    raise
                except RepositorySecurityError:
                    raise
                except (PermissionError, OSError):
                    continue

    async def retrieve(
        self,
        source_reference: str,
        branch: str | None = None,
        analysis_id=None,
    ) -> RepositorySnapshot:
        source_text = self._validate_nonempty_source(source_reference)
        source = self._validate_directory(source_text)
        analysis_uuid = UUID(str(analysis_id)) if analysis_id else uuid4()
        workspace = self.workspace_manager.create_workspace(analysis_uuid)
        workspace_id = self.workspace_manager.workspace_id_for_path(workspace) or uuid4()
        started = time.perf_counter()
        try:
            await asyncio.to_thread(self._copy_repository, source, workspace)
            files = await asyncio.to_thread(FileDiscovery().discover, workspace)
            snapshot = RepositorySnapshot(
                analysis_id=analysis_uuid,
                source_type="local",
                repository_name=source.name,
                source_reference=source.name,
                branch=branch,
                workspace_id=workspace_id,
                files=files,
                total_files=len(files),
                total_size_bytes=sum(file.size_bytes for file in files),
                created_at=datetime.now(timezone.utc),
            )
            return snapshot
        except Exception:
            self.workspace_manager.cleanup_workspace(workspace)
            raise
