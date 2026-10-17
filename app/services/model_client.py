
from app.config.settings import settings, validate_model_settings


def create_model_client():
    """Create the chat client selected by configuration."""

    validate_model_settings()

    provider = settings.model_provider.lower()

    if provider == "ollama":
        from agent_framework_ollama import OllamaChatClient

        return OllamaChatClient(
            host=settings.ollama_base_url,
            model=settings.ollama_model,
        )

    if provider == "openai":
        from agent_framework.openai import OpenAIChatClient

        return OpenAIChatClient(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
        )

    raise ValueError(f"Unsupported model provider: {provider}")