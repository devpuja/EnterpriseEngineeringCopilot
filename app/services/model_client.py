from app.config.settings import settings, validate_model_settings


def create_model_client():
    """Create the MAF chat client selected by environment configuration."""
    validate_model_settings()
    provider = settings.model_provider.lower()

    if provider == "openai":
        from agent_framework.openai import OpenAIChatClient
        from app.observability.usage import UsageMiddleware

        return OpenAIChatClient(api_key=settings.openai_api_key, model=settings.openai_model,
                                middleware=[UsageMiddleware()])

    raise ValueError(f"Unsupported model provider: {provider}")
