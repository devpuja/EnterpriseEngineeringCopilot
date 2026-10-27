from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str
    app_env: str
    log_level: str

    model_provider: str = "openai"

    openai_api_key: str = ""
    openai_model: str = ""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()  # pyright: ignore[reportCallIssue]


def validate_model_settings() -> None:
    provider = settings.model_provider.lower()

    if provider != "openai":
        raise ValueError("MODEL_PROVIDER must be 'openai'.")

    if not settings.openai_api_key:
        raise ValueError("Set OPENAI_API_KEY in your .env file.")
    if not settings.openai_model:
        raise ValueError("Set OPENAI_MODEL in your .env file.")
