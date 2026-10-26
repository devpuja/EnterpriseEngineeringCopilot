from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str
    app_env: str
    log_level: str

    model_provider: str

    openai_api_key: str = ""
    openai_model: str = ""

    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_chat_deployment: str = ""
    azure_openai_embedding_deployment: str = ""
    azure_openai_api_version: str = "2024-10-21"

    foundry_openai_endpoint: str = ""
    foundry_project_endpoint: str = ""
    foundry_model: str = ""
    foundry_embedding_model: str = ""

    rag_backend: str = "azure"
    rag_embedding_dimensions: int = 1536
    rag_chunk_size: int = 1200
    rag_chunk_overlap: int = 150

    azure_search_endpoint: str = ""
    azure_search_index_name: str = "engineering-knowledge-v2"
    azure_search_api_key: str = ""

    azure_storage_account_url: str = ""
    azure_storage_container: str = "engineering-documents"
    azure_storage_connection_string: str = ""

    entra_tenant_id: str = ""
    entra_api_client_id: str = ""
    entra_required_scope: str = "access_as_user"

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()  # pyright: ignore[reportCallIssue]


def validate_model_settings() -> None:
    provider = settings.model_provider.lower()

    if provider not in {"openai", "azure_openai", "foundry"}:
        raise ValueError(
            "MODEL_PROVIDER must be 'openai', 'azure_openai', or 'foundry'."
        )

    if provider == "openai":
        if not settings.openai_api_key:
            raise ValueError("Set OPENAI_API_KEY in your .env file.")
        if not settings.openai_model:
            raise ValueError("Set OPENAI_MODEL in your .env file.")

    if provider == "azure_openai":
        if not settings.azure_openai_endpoint or not settings.azure_openai_chat_deployment:
            raise ValueError(
                "Set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_CHAT_DEPLOYMENT."
            )

    if provider == "foundry":
        if not settings.foundry_openai_endpoint or not settings.foundry_model:
            raise ValueError(
                "Set FOUNDRY_OPENAI_ENDPOINT and FOUNDRY_MODEL in your .env file."
            )
