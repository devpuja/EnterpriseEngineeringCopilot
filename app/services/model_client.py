from app.config.settings import settings, validate_model_settings


def create_model_client():
    """Create the MAF chat client selected by environment configuration."""
    validate_model_settings()
    provider = settings.model_provider.lower()

    if provider == "openai":
        from agent_framework.openai import OpenAIChatClient

        return OpenAIChatClient(api_key=settings.openai_api_key, model=settings.openai_model)

    if provider == "azure_openai":
        from agent_framework.azure import AzureOpenAIChatClient

        client_args = {
            "endpoint": settings.azure_openai_endpoint,
            "deployment_name": settings.azure_openai_chat_deployment,
            "api_version": settings.azure_openai_api_version,
        }
        if settings.azure_openai_api_key:
            client_args["api_key"] = settings.azure_openai_api_key
        else:
            from azure.identity import DefaultAzureCredential

            client_args["credential"] = DefaultAzureCredential()
        return AzureOpenAIChatClient(**client_args)

    if provider == "foundry":
        from agent_framework.foundry import FoundryChatClient
        from azure.identity import AzureCliCredential

        return FoundryChatClient(
            project_endpoint=settings.foundry_project_endpoint,
            model=settings.foundry_model,
            credential=AzureCliCredential(),
        )

    raise ValueError(f"Unsupported model provider: {provider}")
