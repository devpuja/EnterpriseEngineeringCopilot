from typing import Protocol, runtime_checkable

from app.repository.models import RepositorySnapshot


@runtime_checkable
class RepositoryAccessContract(Protocol):
    async def retrieve(
        self,
        source_reference: str,
        branch: str | None = None,
        analysis_id=None,
    ) -> RepositorySnapshot:
        ...
