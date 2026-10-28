import asyncio
from collections.abc import Sequence

from fastapi import APIRouter, HTTPException, UploadFile, File

from app.api.schemas import IndexedDocument, RAGAnswer, RAGQuery
from app.config.settings import settings, validate_rag_settings
from app.services.document_ingestion import (
    DocumentIngestionError,
    FileTooLargeError,
    UnsupportedFileError,
)
from app.services.document_repository import DocumentRepository
from app.services.embedding_service import EmbeddingProvider, EmbeddingServiceError, OpenAIEmbeddingService
from app.services.rag_service import RAGService
from app.services.vector_store import ChromaVectorStore

router = APIRouter(prefix="/api/v1/rag", tags=["RAG"])


def _create_embedding_provider() -> EmbeddingProvider:
    if not settings.openai_api_key:
        raise EmbeddingServiceError("Set OPENAI_API_KEY before uploading or querying documents.")
    return OpenAIEmbeddingService(
        api_key=settings.openai_api_key,
        model=settings.openai_embedding_model,
        timeout_seconds=settings.embedding_timeout_seconds,
        max_retries=settings.embedding_max_retries,
    )


validate_rag_settings()
_embedding_provider: EmbeddingProvider | None = None
_vector_store = ChromaVectorStore(
    persist_directory=settings.chroma_persist_directory,
    collection_name=settings.chroma_collection_name,
)
_repository = DocumentRepository(settings.rag_metadata_database)


def get_embedding_provider() -> EmbeddingProvider:
    global _embedding_provider
    if _embedding_provider is None:
        _embedding_provider = _create_embedding_provider()
    return _embedding_provider


def get_rag_service() -> RAGService:
    return RAGService(
        embedding_provider=get_embedding_provider(),
        vector_store=_vector_store,
        repository=_repository,
        document_directory=settings.document_storage_directory,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        top_k=settings.rag_top_k,
        context_char_limit=settings.rag_context_char_limit,
        adjacent_chunk_radius=settings.rag_adjacent_chunk_radius,
        source_excerpt_char_limit=settings.rag_source_excerpt_char_limit,
    )


@router.post("/documents", response_model=IndexedDocument, status_code=201)
async def upload_document(file: UploadFile = File(...)) -> IndexedDocument:
    try:
        content = await file.read(settings.max_upload_size_bytes + 1)
        # I/O-heavy extraction and embedding run in a worker thread.
        import anyio
        service = get_rag_service()
        record = await anyio.to_thread.run_sync(
            lambda: asyncio.run(service.ingest(
                filename=file.filename or "",
                media_type=file.content_type or "",
                content=content,
                max_upload_size=settings.max_upload_size_bytes,
            ))
        )
        return IndexedDocument.model_validate(record)
    except FileTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except UnsupportedFileError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except DocumentIngestionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except EmbeddingServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Document ingestion failed. Check application logs.") from exc


@router.get("/documents", response_model=list[IndexedDocument])
async def list_documents() -> list[IndexedDocument]:
    service = get_rag_service_embeddedless()
    return [IndexedDocument.model_validate(record) for record in service.list_documents()]


def get_rag_service_embeddedless() -> RAGService:
    try:
        embedding = get_embedding_provider()
    except EmbeddingServiceError:
        embedding = None
    return RAGService(
        embedding_provider=embedding or _UnusedEmbeddingProvider(),
        vector_store=_vector_store,
        repository=_repository,
        document_directory=settings.document_storage_directory,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        top_k=settings.rag_top_k,
        context_char_limit=settings.rag_context_char_limit,
        adjacent_chunk_radius=settings.rag_adjacent_chunk_radius,
        source_excerpt_char_limit=settings.rag_source_excerpt_char_limit,
    )


class _UnusedEmbeddingProvider(EmbeddingProvider):
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        raise EmbeddingServiceError("Set OPENAI_API_KEY before generating embeddings.")


@router.get("/documents/{document_id}", response_model=IndexedDocument)
async def get_document(document_id: str) -> IndexedDocument:
    record = get_rag_service_embeddedless().get_document(document_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Indexed document not found.")
    return IndexedDocument.model_validate(record)


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(document_id: str) -> None:
    deleted = get_rag_service_embeddedless().delete_document(document_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Indexed document not found.")


@router.post("/query", response_model=RAGAnswer)
async def query_documents(request: RAGQuery) -> RAGAnswer:
    try:
        service = get_rag_service()
        return await service.answer(request.question, top_k=request.top_k)
    except EmbeddingServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="RAG query failed. Check application logs.") from exc
