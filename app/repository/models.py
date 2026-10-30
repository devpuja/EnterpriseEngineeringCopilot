from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class RepositoryFile(BaseModel):
    relative_path: str = Field(min_length=1)
    file_name: str = Field(min_length=1)
    extension: str
    size_bytes: int = Field(ge=0)
    content_hash: str | None = None
    is_binary: bool = False
    language: str | None = None
    technologies: list[str] = Field(default_factory=list)


class RepositorySnapshot(BaseModel):
    analysis_id: UUID = Field(default_factory=uuid4)
    source_type: Literal["local", "github"]
    repository_name: str = Field(min_length=1)
    source_reference: str = Field(min_length=1)
    branch: str | None = None
    commit_sha: str | None = None
    workspace_id: UUID
    files: list[RepositoryFile] = Field(default_factory=list)
    total_files: int = Field(ge=0)
    total_size_bytes: int = Field(ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
