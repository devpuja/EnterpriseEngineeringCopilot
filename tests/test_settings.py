import os
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast
from unittest.mock import patch

from app.config.settings import Settings


_SETTINGS_VALUES = {
    "APP_NAME": "Test App",
    "APP_ENV": "test",
    "LOG_LEVEL": "INFO",
    "MODEL_PROVIDER": "ollama",
    "OLLAMA_BASE_URL": "http://localhost:11434",
    "OLLAMA_MODEL": "test-model",
    "OPENAI_API_KEY": "",
    "OPENAI_MODEL": "test-model",
}


def test_settings_load_values_from_env_file():
    with TemporaryDirectory() as directory:
        env_file = Path(directory) / ".env"
        env_file.write_text(
            "\n".join(
                f"{name}={value}"
                for name, value in _SETTINGS_VALUES.items()
            ),
            encoding="utf-8",
        )

        with patch.dict(os.environ, {}, clear=True):
            config = cast(Any, Settings)(_env_file=env_file)

    assert config.model_provider == "ollama"
    assert config.ollama_model == "test-model"


def test_settings_fields_are_required():
    assert all(
        field.is_required()
        for field in Settings.model_fields.values()
    )


def test_provider_name_is_case_insensitive():
    config = Settings(
        app_name="Test App",
        app_env="test",
        log_level="INFO",
        model_provider="OPENAI",
        ollama_base_url="http://localhost:11434",
        ollama_model="test-model",
        openai_api_key="",
        openai_model="test-model",
    )

    assert config.model_provider.lower() == "openai"
