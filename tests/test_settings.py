import os
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast
from unittest.mock import patch

import pytest

from app.config.settings import Settings, validate_model_settings


_SETTINGS_VALUES = {
    "APP_NAME": "Test App",
    "APP_ENV": "test",
    "LOG_LEVEL": "INFO",
    "MODEL_PROVIDER": "openai",
    "OPENAI_API_KEY": "test-key",
    "OPENAI_MODEL": "test-model",
}


def test_settings_load_values_from_env_file():
    with TemporaryDirectory() as directory:
        env_file = Path(directory) / ".env"
        env_file.write_text(
            "\n".join(f"{name}={value}" for name, value in _SETTINGS_VALUES.items()),
            encoding="utf-8",
        )

        with patch.dict(os.environ, {}, clear=True):
            config = cast(Any, Settings)(_env_file=env_file)

    assert config.model_provider == "openai"
    assert config.openai_model == "test-model"


def test_model_provider_defaults_to_openai():
    env_values = {
        key: value
        for key, value in _SETTINGS_VALUES.items()
        if key != "MODEL_PROVIDER"
    }
    with patch.dict(os.environ, env_values, clear=True):
        config = cast(Any, Settings)(_env_file=None)

    assert config.model_provider == "openai"


def test_environment_overrides_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_MODEL=file-model\n", encoding="utf-8")
    with patch.dict(
        os.environ, {**_SETTINGS_VALUES, "OPENAI_MODEL": "environment-model"}, clear=True
    ):
        config = cast(Any, Settings)(_env_file=env_file)

    assert config.openai_model == "environment-model"


def test_only_common_settings_fields_are_required():
    assert {
        name for name, field in Settings.model_fields.items() if field.is_required()
    } == {"app_name", "app_env", "log_level"}


def test_removed_integrations_have_no_settings():
    assert not {
        "azure_openai_endpoint",
        "foundry_project_endpoint",
        "azure_search_endpoint",
        "azure_storage_account_url",
        "entra_tenant_id",
        "rag_backend",
    }.intersection(Settings.model_fields)


def test_openai_provider_requires_key_and_model():
    with patch.dict(os.environ, {}, clear=True):
        config = cast(Any, Settings)(
            _env_file=None,
            app_name="Test App",
            app_env="test",
            log_level="INFO",
            model_provider="OPENAI",
            openai_api_key="test-key",
            openai_model="test-model",
        )

    with patch("app.config.settings.settings", config):
        validate_model_settings()


@pytest.mark.parametrize(
    ("api_key", "model", "missing_setting"),
    [
        ("", "test-model", "OPENAI_API_KEY"),
        ("test-key", "", "OPENAI_MODEL"),
    ],
)
def test_openai_provider_requires_its_settings(api_key, model, missing_setting):
    with patch.dict(os.environ, {}, clear=True):
        config = cast(Any, Settings)(
            _env_file=None,
            app_name="Test App",
            app_env="test",
            log_level="INFO",
            model_provider="openai",
            openai_api_key=api_key,
            openai_model=model,
        )

    with patch("app.config.settings.settings", config):
        with pytest.raises(ValueError, match=missing_setting):
            validate_model_settings()


def test_unknown_provider_is_rejected():
    with patch.dict(os.environ, {}, clear=True):
        config = cast(Any, Settings)(
            _env_file=None,
            app_name="Test App",
            app_env="test",
            log_level="INFO",
            model_provider="unsupported",
        )

    with patch("app.config.settings.settings", config):
        with pytest.raises(ValueError, match="MODEL_PROVIDER"):
            validate_model_settings()


def test_provider_name_is_case_insensitive():
    config = Settings(
        app_name="Test App",
        app_env="test",
        log_level="INFO",
        model_provider="OPENAI",
        openai_api_key="",
        openai_model="test-model",
    )

    assert config.model_provider.lower() == "openai"
