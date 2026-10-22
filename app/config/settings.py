from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str
    app_env: str
    log_level: str

    model_provider: str

    ollama_base_url: str
    ollama_model: str

    openai_api_key: str
    openai_model: str

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()  # pyright: ignore[reportCallIssue]


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
