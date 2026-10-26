from __future__ import annotations

import asyncio
from typing import Protocol

from openai import APIStatusError

from app.config.settings import settings


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> list[float]: ...


class AzureOpenAIEmbeddingProvider:
    """Legacy embedding adapter for a standalone Azure OpenAI deployment."""

    def __init__(self) -> None:
        from openai import AzureOpenAI

        endpoint = settings.azure_openai_endpoint.strip()
        deployment = settings.azure_openai_embedding_deployment.strip()
        api_key = settings.azure_openai_api_key.strip()
        api_version = settings.azure_openai_api_version.strip()
        if not endpoint or not deployment:
            raise RuntimeError(
                "Azure embeddings require AZURE_OPENAI_ENDPOINT and "
                "AZURE_OPENAI_EMBEDDING_DEPLOYMENT."
            )
        client_args = {
            "azure_endpoint": endpoint,
            "api_version": api_version,
        }
        if api_key:
            client_args["api_key"] = api_key
        else:
            from azure.identity import DefaultAzureCredential, get_bearer_token_provider

            credential = DefaultAzureCredential()
            client_args["azure_ad_token_provider"] = get_bearer_token_provider(
                credential, "https://cognitiveservices.azure.com/.default"
            )
        self._deployment = deployment
        self._client = AzureOpenAI(**client_args)

    def embed(self, text: str) -> list[float]:
        response = self._client.embeddings.create(model=self._deployment, input=text)
        return list(response.data[0].embedding)



class FoundryEmbeddingProvider:
    """Embedding provider using the Foundry OpenAI-compatible endpoint."""

    def __init__(self) -> None:
        from openai import OpenAI
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider

        self._endpoint = settings.foundry_openai_endpoint.strip()
        self._model = settings.foundry_embedding_model.strip()
        self._dimensions = settings.rag_embedding_dimensions

        if not self._endpoint:
            raise RuntimeError("FOUNDRY_OPENAI_ENDPOINT must be configured.")
        if not self._model:
            raise RuntimeError("FOUNDRY_EMBEDDING_MODEL must be configured.")

        credential = DefaultAzureCredential()
        token_provider = get_bearer_token_provider(
            credential,
            "https://ai.azure.com/.default",
        )

        self._client = OpenAI(
            base_url=self._endpoint,
            api_key=token_provider,
        )

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        try:
            response = self._client.embeddings.create(
                model=self._model,
                input=texts,
                )
        except APIStatusError as exc:
                print("Embedding HTTP status:", exc.status_code)
                print("Embedding error:", str(exc))
                print("Request ID:", exc.request_id)
                print("Response headers:", {
                    key: exc.response.headers.get(key)
                    for key in (
                        "retry-after",
                        "retry-after-ms",
                        "x-ratelimit-limit-requests",
                        "x-ratelimit-remaining-requests",
                        "x-ratelimit-reset-requests",
                    )
                    if exc.response.headers.get(key) is not None
                })
                raise
        
        vectors = [
            list(item.embedding)
            for item in sorted(response.data, key=lambda item: item.index)
        ]

        if len(vectors) != len(texts):
            raise RuntimeError(
                f"Expected {len(texts)} embeddings, received {len(vectors)}."
            )

        for vector in vectors:
            if len(vector) != self._dimensions:
                raise ValueError(
                    f"Expected {self._dimensions} dimensions, "
                    f"received {len(vector)}."
                )

        return vectors

    def embed(self, text: str) -> list[float]:
        return self.embed_many([text])[0]