from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str
    app_env: str
    log_level: str

    model_provider: str = "openai"

    openai_api_key: str = ""
    openai_model: str = ""

    openai_embedding_model: str = "text-embedding-3-small"
    chroma_persist_directory: str = "rag_data/chroma"
    chroma_collection_name: str = "engineering_documents"
    document_storage_directory: str = "rag_data/documents"
    rag_metadata_database: str = "rag_data/metadata.db"
    max_upload_size_bytes: int = 10_485_760
    chunk_size: int = 1000
    chunk_overlap: int = 150
    rag_top_k: int = 5
    rag_context_char_limit: int = 12_000
    rag_adjacent_chunk_radius: int = 2
    rag_source_excerpt_char_limit: int = 500
    embedding_timeout_seconds: float = 30
    embedding_max_retries: int = 3

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()  # pyright: ignore[reportCallIssue]


def validate_rag_settings() -> None:
    if settings.chunk_size < 100:
        raise ValueError("CHUNK_SIZE must be at least 100.")
    if settings.chunk_overlap < 0:
        raise ValueError("CHUNK_OVERLAP must not be negative.")
    if settings.chunk_overlap >= settings.chunk_size:
        raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE.")
    if settings.max_upload_size_bytes <= 0:
        raise ValueError("MAX_UPLOAD_SIZE_BYTES must be positive.")
    if settings.rag_top_k <= 0:
        raise ValueError("RAG_TOP_K must be positive.")
    if settings.rag_context_char_limit <= 0:
        raise ValueError("RAG_CONTEXT_CHAR_LIMIT must be positive.")
    if settings.rag_adjacent_chunk_radius < 0 or settings.rag_adjacent_chunk_radius > 5:
        raise ValueError("RAG_ADJACENT_CHUNK_RADIUS must be between 0 and 5.")
    if settings.rag_source_excerpt_char_limit <= 0:
        raise ValueError("RAG_SOURCE_EXCERPT_CHAR_LIMIT must be positive.")
    if settings.embedding_timeout_seconds <= 0:
        raise ValueError("EMBEDDING_TIMEOUT_SECONDS must be positive.")
    if settings.embedding_max_retries < 0:
        raise ValueError("EMBEDDING_MAX_RETRIES must not be negative.")


def validate_model_settings() -> None:
    provider = settings.model_provider.lower()

    if provider != "openai":
        raise ValueError("MODEL_PROVIDER must be 'openai'.")

    if not settings.openai_api_key:
        raise ValueError("Set OPENAI_API_KEY in your .env file.")
    if not settings.openai_model:
        raise ValueError("Set OPENAI_MODEL in your .env file.")
