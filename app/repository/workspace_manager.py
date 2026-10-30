import logging
import shutil
import threading
import time
from pathlib import Path
from uuid import UUID, uuid4

from app.config.settings import settings
from app.repository.exceptions import WorkspaceError


logger = logging.getLogger(__name__)


class WorkspaceManager:
    def __init__(
        self,
        workspace_root: str | Path | None = None,
        retention_seconds: int | None = None,
        maximum_storage_bytes: int | None = None,
    ):
        root = workspace_root or settings.repository_workspace_root
        self.workspace_root = Path(root).expanduser().resolve()
        self.retention_seconds = retention_seconds if retention_seconds is not None else settings.workspace_retention_seconds
        self.maximum_storage_bytes = maximum_storage_bytes or settings.maximum_repository_size_bytes
        self._lock = threading.RLock()
        self._workspaces: dict[UUID, dict[str, object]] = {}

        if self.workspace_root.is_symlink():
            raise WorkspaceError("Workspace root must not be a symlink.")
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    def create_workspace(self, analysis_id: UUID | None = None) -> Path:
        analysis_id = analysis_id or uuid4()
        workspace_id = uuid4()
        workspace = self.workspace_root / str(workspace_id)
        try:
            self.cleanup_expired_workspaces()
            existing_size = sum(
                file.stat().st_size
                for directory in self.workspace_root.iterdir()
                if directory.is_dir() and not directory.is_symlink()
                for file in directory.rglob("*")
                if file.is_file() and not file.is_symlink()
            ) if self.workspace_root.exists() else 0
            if existing_size >= self.maximum_storage_bytes:
                raise WorkspaceError("Repository workspace storage limit exceeded.")
            workspace.mkdir(parents=True, exist_ok=False)
            with self._lock:
                self._workspaces[workspace_id] = {
                    "analysis_id": analysis_id,
                    "created_at": time.time(),
                    "active": True,
                    "path": workspace,
                }
            logger.info(
                "event=workspace_created analysis_id=%s workspace_id=%s",
                analysis_id, workspace_id,
            )
            return workspace
        except (OSError, FileExistsError) as exc:
            raise WorkspaceError("Unable to create repository workspace.") from exc

    def workspace_id_for_path(self, workspace: Path) -> UUID | None:
        workspace = workspace.resolve()
        for workspace_id, metadata in self._workspaces.items():
            if Path(str(metadata["path"])).resolve() == workspace:
                return workspace_id
        return None

    def _validate_workspace_path(self, workspace: Path) -> Path:
        try:
            root = self.workspace_root.resolve(strict=True)
            if workspace.is_symlink():
                raise WorkspaceError("Refusing symlink workspace cleanup.")
            resolved = workspace.resolve(strict=True)
            if resolved == root or root not in resolved.parents:
                raise WorkspaceError("Refusing cleanup outside the workspace root.")
            if resolved.parent != root:
                raise WorkspaceError("Workspace cleanup requires a direct workspace child.")
            current = root
            for component in resolved.relative_to(root).parts:
                current = current / component
                if current.is_symlink():
                    raise WorkspaceError("Refusing cleanup through a symlink.")
            return resolved
        except WorkspaceError:
            raise
        except (FileNotFoundError, RuntimeError, OSError) as exc:
            raise WorkspaceError("Workspace path is invalid.") from exc

    def cleanup_workspace(self, workspace: Path | UUID | str) -> bool:
        if isinstance(workspace, (UUID, str)):
            workspace_id = workspace if isinstance(workspace, UUID) else UUID(str(workspace))
            metadata = self._workspaces.get(workspace_id)
            workspace = Path(metadata["path"]) if metadata else self.workspace_root / str(workspace_id)
        else:
            workspace_id = self.workspace_id_for_path(workspace)

        if not workspace.exists():
            with self._lock:
                if workspace_id:
                    self._workspaces.pop(workspace_id, None)
            return True
        logger.info("event=workspace_cleanup_started workspace_id=%s", workspace_id)
        try:
            resolved = self._validate_workspace_path(workspace)
            with self._lock:
                metadata = self._workspaces.get(workspace_id) if workspace_id else None
                if metadata and metadata.get("active"):
                    metadata["active"] = False
            quarantine = self.workspace_root / f".cleanup-{uuid4()}"
            resolved.rename(quarantine)
            if quarantine.is_symlink():
                quarantine.unlink()
            else:
                shutil.rmtree(quarantine)
            with self._lock:
                if workspace_id:
                    self._workspaces.pop(workspace_id, None)
            logger.info("event=workspace_cleanup_completed workspace_id=%s", workspace_id)
            return True
        except Exception as exc:
            logger.warning("event=workspace_cleanup_failed workspace_id=%s error_type=%s", workspace_id, type(exc).__name__)
            if isinstance(exc, WorkspaceError):
                raise
            raise WorkspaceError("Unable to clean up repository workspace.") from exc

    def cleanup_expired_workspaces(self) -> int:
        expired = time.time() - self.retention_seconds
        cleaned = 0
        with self._lock:
            candidates = [
                (workspace_id, Path(str(metadata["path"])))
                for workspace_id, metadata in list(self._workspaces.items())
                if float(metadata["created_at"]) < expired
            ]
            known_paths = {Path(str(metadata["path"])) for metadata in self._workspaces.values()}

        if self.workspace_root.exists():
            for path in self.workspace_root.iterdir():
                if (
                    path.is_dir()
                    and not path.is_symlink()
                    and path.name != ".cleanup"
                    and path not in known_paths
                    and path.stat().st_mtime < expired
                ):
                    try:
                        workspace_id = UUID(path.name)
                    except ValueError:
                        continue
                    candidates.append((workspace_id, path))
        for workspace_id, path in candidates:
            if self.cleanup_workspace(workspace_id):
                cleaned += 1
        return cleaned
