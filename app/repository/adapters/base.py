from abc import ABC, abstractmethod
from pathlib import Path

from app.repository.exceptions import InvalidRepositorySourceError
from app.repository.models import RepositorySnapshot


class BaseRepositoryAdapter(ABC):
    def _validate_nonempty_source(self, source_reference: str) -> str:
        if not isinstance(source_reference, str) or not source_reference.strip():
            raise InvalidRepositorySourceError("Repository source is required.")
        return source_reference.strip()

    def _safe_resolved_path(self, value: str | Path) -> Path:
        try:
            return Path(value).expanduser().resolve(strict=True)
        except (FileNotFoundError, RuntimeError, OSError) as exc:
            raise InvalidRepositorySourceError("Repository path does not exist or is inaccessible.") from exc

    @abstractmethod
    async def retrieve(
        self,
        source_reference: str,
        branch: str | None = None,
        analysis_id=None,
    ) -> RepositorySnapshot:
        ...
