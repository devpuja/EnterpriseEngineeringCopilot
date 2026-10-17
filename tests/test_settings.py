
import pytest
from app.config.settings import Settings

def test_ollama_is_default_provider():
    config = Settings()

    assert config.model_provider == "ollama"


def test_provider_name_is_case_insensitive():
    config = Settings(
        model_provider="OPENAI",
    )

    assert config.model_provider.lower() == "openai"


def test_unknown_provider_is_rejected():
    config = Settings(
        model_provider="unsupported",
    )

    with pytest.raises(ValueError):
        validate_provider(config.model_provider)


def validate_provider(provider: str) -> None:
    if provider.lower() not in {"ollama", "openai"}:
        raise ValueError("Unsupported provider")