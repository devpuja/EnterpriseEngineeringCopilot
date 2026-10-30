from pathlib import Path
from pathlib import PurePosixPath
import logging

from app.config.settings import settings
from app.repository.exceptions import RepositorySecurityError, WorkspaceError
from app.repository.models import RepositoryFile, RepositorySnapshot
from app.repository.workspace_manager import WorkspaceManager


logger = logging.getLogger(__name__)


class SnapshotContentReader:
    def __init__(self, workspace_manager: WorkspaceManager | None = None):
        self.workspace_manager = workspace_manager or WorkspaceManager()
        self.workspace_manager.workspace_root.resolve(strict=True)

    def repository_root(self, snapshot: RepositorySnapshot) -> Path:
        workspace = (self.workspace_manager.workspace_root / str(snapshot.workspace_id)).resolve(strict=False)
        try:
            root = workspace.resolve(strict=True)
        except (FileNotFoundError, RuntimeError, OSError) as exc:
            raise WorkspaceError("Repository workspace is unavailable.") from exc
        if workspace.is_symlink() or root.parent != self.workspace_manager.workspace_root.resolve(strict=True):
            raise RepositorySecurityError("Repository workspace failed path validation.")
        if snapshot.source_type == "github":
            candidate = root / "repository"
            if candidate.exists():
                root = candidate.resolve(strict=True)
        if root.is_symlink():
            raise RepositorySecurityError("Repository root must not be a symlink.")
        return root

    def read_text(self, snapshot: RepositorySnapshot, file: RepositoryFile, max_bytes: int | None = None) -> str | None:
        if file.is_binary:
            return None
        limit = max_bytes or settings.maximum_repository_file_size_bytes
        if file.size_bytes > limit:
            logger.warning("event=analysis_file_skipped reason=size_limit relative_path=%s", file.relative_path)
            return None
        try:
            root = self.repository_root(snapshot).resolve(strict=True)
            relative = PurePosixPath(file.relative_path)
            path = (root.joinpath(*relative.parts)).resolve(strict=True)
            if root not in path.parents and path != root:
                raise RepositorySecurityError("Analysis file escapes the repository workspace.")
            if path.is_symlink():
                raise RepositorySecurityError("Analysis does not follow workspace symlinks.")
            if not path.is_file():
                return None
            if path.stat().st_size > limit:
                return None
            return path.read_text(encoding="utf-8", errors="replace")
        except RepositorySecurityError:
            raise
        except (FileNotFoundError, RuntimeError, OSError):
            return None
