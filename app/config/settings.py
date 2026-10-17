
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Enterprise Engineering Copilot"
    app_env: str = "development"
    log_level: str = "INFO"

    # Select: ollama or openai
    model_provider: str = "ollama"

    # Ollama configuration
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:latest"

    # OpenAI configuration
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()


def validate_model_settings() -> None:
    provider = settings.model_provider.lower()

    if provider not in {"ollama", "openai"}:
        raise ValueError(
            "MODEL_PROVIDER must be 'ollama' or 'openai'."
        )

    if provider == "ollama" and not settings.ollama_model:
        raise ValueError(
            "Set OLLAMA_MODEL in your .env file."
        )

    if provider == "openai" and not settings.openai_api_key:
        raise ValueError(
            "Set OPENAI_API_KEY in your .env file."
        )