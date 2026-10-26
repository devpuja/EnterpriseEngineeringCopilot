from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class DocumentChunk:
    chunk_id: str
    document_id: str
    tenant_id: str
    file_name: str
    version: int
    chunk_index: int
    content: str
    content_hash: str
    page_number: int | None = None
    is_active: bool = True
    uploaded_at: str = ""

    def to_search_document(self, vector: list[float] | None = None) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "tenant_id": self.tenant_id,
            "file_name": self.file_name,
            "version": self.version,
            "chunk_index": self.chunk_index,
            "content": self.content,
            "content_hash": self.content_hash,
            "page_number": self.page_number or 0,
            "is_active": self.is_active,
            "uploaded_at": self.uploaded_at or utc_now_iso(),
        }
        if vector is not None:
            doc["content_vector"] = vector
        return doc


class IngestResponse(BaseModel):
    document_id: str
    file_name: str
    version: int = 1
    chunk_count: int
    status: str = "indexed"


class QueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=4000)
    top_k: int = Field(default=5, ge=1, le=20)


class RetrievedChunk(BaseModel):
    chunk_id: str
    document_id: str
    file_name: str
    version: int
    chunk_index: int
    content: str
    score: float = 0.0
    page_number: int | None = None


class QueryResponse(BaseModel):
    answer: str
    citations: list[RetrievedChunk]
    retrieval_count: int
