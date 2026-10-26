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


@pytest.mark.parametrize("backend", ["memory", "azure"])
def test_settings_load_values_from_env_file(backend: str):
    with TemporaryDirectory() as directory:
        env_file = Path(directory) / ".env"
        env_file.write_text(
            "\n".join(
                f"{name}={value}"
                for name, value in {**_SETTINGS_VALUES, "RAG_BACKEND": backend}.items()
            ),
            encoding="utf-8",
        )

        with patch.dict(os.environ, {}, clear=True):
            config = cast(Any, Settings)(_env_file=env_file)

    assert config.model_provider == "openai"
    assert config.openai_model == "test-model"
    assert config.rag_backend == backend


def test_rag_backend_defaults_to_memory():
    with patch.dict(os.environ, _SETTINGS_VALUES, clear=True):
        config = cast(Any, Settings)(_env_file=None)

    assert config.rag_backend == "memory"


def test_rag_backend_environment_overrides_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("RAG_BACKEND=azure\n", encoding="utf-8")
    with patch.dict(
        os.environ, {**_SETTINGS_VALUES, "RAG_BACKEND": "memory"}, clear=True
    ):
        config = cast(Any, Settings)(_env_file=env_file)

    assert config.rag_backend == "memory"


@pytest.mark.parametrize(
    ("name", "value", "default"),
    [
        ("azure_search_endpoint", "https://example.search.windows.net", ""),
        ("azure_search_index_name", "test-index", "engineering-knowledge-v2"),
        ("azure_search_api_key", "test-search-key", ""),
        ("azure_storage_account_url", "https://example.blob.core.windows.net", ""),
        ("azure_storage_container", "test-documents", "engineering-documents"),
        ("azure_storage_connection_string", "test-connection-string", ""),
        ("azure_openai_embedding_deployment", "test-embeddings", ""),
        ("rag_embedding_dimensions", 3072, 1536),
        ("rag_chunk_size", 600, 1200),
        ("rag_chunk_overlap", 50, 150),
        ("entra_tenant_id", "test-tenant", ""),
        ("entra_api_client_id", "test-client", ""),
        ("entra_required_scope", "test-scope", "access_as_user"),
    ],
)
def test_rag_settings_defaults_file_and_environment(tmp_path, name, value, default):
    env_file = tmp_path / ".env"
    env_file.write_text(f"{name.upper()}={value}\n", encoding="utf-8")
    with patch.dict(os.environ, _SETTINGS_VALUES, clear=True):
        config = cast(Any, Settings)(_env_file=None)
        assert getattr(config, name) == default

        config = cast(Any, Settings)(_env_file=env_file)
        assert getattr(config, name) == value

        with patch.dict(os.environ, {name.upper(): str(default)}):
            config = cast(Any, Settings)(_env_file=env_file)
            assert getattr(config, name) == default


def test_only_common_settings_fields_are_required():
    assert {
        name for name, field in Settings.model_fields.items() if field.is_required()
    } == {"app_name", "app_env", "log_level", "model_provider"}


_PROVIDER_VALUES = {
    "openai": {
        "openai_api_key": "test-key",
        "openai_model": "test-model",
    },
    "azure_openai": {
        "azure_openai_endpoint": "https://example.openai.azure.com",
        "azure_openai_chat_deployment": "test-model",
    },
    "foundry": {
        "foundry_project_endpoint": "https://example.services.ai.azure.com/api/projects/test",
        "foundry_model": "test-model",
    },
}


@pytest.mark.parametrize("provider", _PROVIDER_VALUES)
def test_selected_provider_does_not_require_other_provider_settings(provider: str):
    with patch.dict(os.environ, {}, clear=True):
        config = cast(Any, Settings)(
            _env_file=None,
            app_name="Test App",
            app_env="test",
            log_level="INFO",
            model_provider=provider.upper(),
            **_PROVIDER_VALUES[provider],
        )

    with patch("app.config.settings.settings", config):
        validate_model_settings()


@pytest.mark.parametrize(
    ("provider", "missing_field"),
    [
        (provider, field)
        for provider, values in _PROVIDER_VALUES.items()
        for field in values
    ],
)
@pytest.mark.parametrize("empty_value", [False, True], ids=["omitted", "empty"])
def test_selected_provider_requires_its_settings(
    provider: str, missing_field: str, empty_value: bool
):
    values = _PROVIDER_VALUES[provider].copy()
    if empty_value:
        values[missing_field] = ""
    else:
        del values[missing_field]

    with patch.dict(os.environ, {}, clear=True):
        config = cast(Any, Settings)(
            _env_file=None,
            app_name="Test App",
            app_env="test",
            log_level="INFO",
            model_provider=provider,
            **values,
        )

    with patch("app.config.settings.settings", config):
        with pytest.raises(ValueError, match=missing_field.upper()):
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
