from pathlib import Path
from typing import Protocol, runtime_checkable

from app.repository.models import RepositoryFile, RepositorySnapshot


class AnalyzerContract(Protocol):
    def analyze(self, snapshot: RepositorySnapshot, reader: "RepositoryContentReader") -> object:
        ...


@runtime_checkable
class RepositoryContentReader(Protocol):
    def read_text(self, snapshot: RepositorySnapshot, file: RepositoryFile, max_bytes: int | None = None) -> str | None:
        ...

    def repository_root(self, snapshot: RepositorySnapshot) -> Path:
        ...
