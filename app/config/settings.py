from pathlib import Path
from urllib.parse import urlparse
from typing import Literal

from pydantic import Field, model_validator

from pydantic_settings import BaseSettings, SettingsConfigDict
from app.observability.models import ModelPricing


class Settings(BaseSettings):
    app_name: str
    app_env: str
    log_level: str
    log_format: Literal["text", "json"] = "text"
    telemetry_enabled: bool = False
    telemetry_exporter: Literal["none", "console", "otlp"] = "none"
    telemetry_sample_ratio: float = Field(default=1.0, ge=0, le=1)
    telemetry_otlp_endpoint: str = ""
    usage_enabled: bool = True
    model_pricing: list[ModelPricing] = Field(default_factory=list)
    rag_require_verified: bool = False
    diagram_require_valid: bool = False

    model_provider: str = "openai"
    auth_issuer: str = ""
    auth_audience: str = ""
    auth_jwks_url: str = ""
    auth_clock_skew_seconds: int = Field(default=30, ge=0, le=300)
    swagger_oauth_client_id: str = ""
    swagger_oauth_scope: str = ""
    approval_timeout_seconds: int = Field(default=900, gt=0, le=86_400)

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
    
    mcp_server_url: str = "http://127.0.0.1:8001/mcp"
    mcp_timeout_seconds: float = Field(default=15.0, gt=0, description="Timeout for MCP server requests in seconds.")

    repository_workspace_root: str = "rag_data/repositories"
    report_artifact_directory: str = "rag_data/reports"
    allowed_local_repository_roots: list[str] = Field(default_factory=list)
    maximum_repository_size_bytes: int = 1_073_741_824
    maximum_repository_file_size_bytes: int = 10_485_760
    maximum_repository_file_count: int = 50_000
    maximum_directory_traversal_depth: int = 20
    workspace_retention_seconds: int = 86_400
    git_executable_path: str = "git"
    github_allowed_hosts: list[str] = Field(default_factory=lambda: ["github.com"])

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_swagger_oauth(self) -> "Settings":
        self.log_level = self.log_level.upper()
        if self.log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR, or CRITICAL.")
        pricing_keys = [(item.provider, item.model) for item in self.model_pricing]
        if len(pricing_keys) != len(set(pricing_keys)):
            raise ValueError("MODEL_PRICING must not contain duplicate provider/model entries.")
        if self.telemetry_exporter == "otlp":
            endpoint = urlparse(self.telemetry_otlp_endpoint)
            if endpoint.scheme not in {"http", "https"} or not endpoint.hostname or endpoint.username or endpoint.password:
                raise ValueError("TELEMETRY_OTLP_ENDPOINT must be an HTTP(S) URL without embedded credentials.")
        self.swagger_oauth_client_id = self.swagger_oauth_client_id.strip()
        self.swagger_oauth_scope = self.swagger_oauth_scope.strip()
        if not self.swagger_oauth_client_id and not self.swagger_oauth_scope:
            return self
        if not self.swagger_oauth_client_id or not self.swagger_oauth_scope:
            raise ValueError(
                "Set both SWAGGER_OAUTH_CLIENT_ID and SWAGGER_OAUTH_SCOPE."
            )
        issuer = urlparse(self.auth_issuer.strip())
        if (
            issuer.scheme != "https"
            or not issuer.netloc
            or issuer.username
            or issuer.password
            or issuer.query
            or issuer.fragment
            or not issuer.path.endswith("/v2.0")
        ):
            raise ValueError("Swagger OAuth requires an HTTPS v2.0 AUTH_ISSUER.")
        if (
            not self.auth_audience.strip()
            or not self.swagger_oauth_scope.startswith(
                f"api://{self.auth_audience.strip()}/"
            )
            or not self.swagger_oauth_scope.rsplit("/", 1)[-1]
            or self.swagger_oauth_scope.endswith("/.default")
            or any(character.isspace() for character in self.swagger_oauth_scope)
        ):
            raise ValueError(
                "SWAGGER_OAUTH_SCOPE must be a named delegated scope "
                "such as api://<AUTH_AUDIENCE>/access_as_user."
            )
        return self


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


def validate_repository_settings() -> None:
    if settings.maximum_repository_size_bytes <= 0:
        raise ValueError("MAXIMUM_REPOSITORY_SIZE_BYTES must be positive.")
    if settings.maximum_repository_file_size_bytes <= 0:
        raise ValueError("MAXIMUM_REPOSITORY_FILE_SIZE_BYTES must be positive.")
    if settings.maximum_repository_file_count <= 0:
        raise ValueError("MAXIMUM_REPOSITORY_FILE_COUNT must be positive.")
    if settings.maximum_directory_traversal_depth < 0:
        raise ValueError("MAXIMUM_DIRECTORY_TRAVERSAL_DEPTH must not be negative.")
    if settings.workspace_retention_seconds <= 0:
        raise ValueError("WORKSPACE_RETENTION_SECONDS must be positive.")


def validate_model_settings() -> None:
    provider = settings.model_provider.lower()

    if provider != "openai":
        raise ValueError("MODEL_PROVIDER must be 'openai'.")

    if not settings.openai_api_key:
        raise ValueError("Set OPENAI_API_KEY in your .env file.")
    if not settings.openai_model:
        raise ValueError("Set OPENAI_MODEL in your .env file.")
