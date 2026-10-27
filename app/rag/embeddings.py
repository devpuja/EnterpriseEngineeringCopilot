from __future__ import annotations
import random
import re
import time

from openai import RateLimitError
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
        if api_key:
            self._client = AzureOpenAI(
                azure_endpoint=endpoint,
                api_version=api_version,
                api_key=api_key,
            )
        else:
            from azure.identity import DefaultAzureCredential, get_bearer_token_provider

            credential = DefaultAzureCredential()
            token_provider = get_bearer_token_provider(
                credential, "https://cognitiveservices.azure.com/.default"
            )
            self._client = AzureOpenAI(
                azure_endpoint=endpoint,
                api_version=api_version,
                azure_ad_token_provider=token_provider,
            )
        self._deployment = deployment

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
            # Retries are handled below so Retry-After is respected consistently.
            max_retries=0,
        )

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        try:
            response = self._create_embeddings_with_retry(texts)
        except APIStatusError as exc:
            # Keep diagnostic information useful when Azure returns a non-retryable
            # error or the bounded retry policy is exhausted.
            print("Embedding HTTP status:", exc.status_code)
            print("Embedding error:", str(exc))
            print("Request ID:", exc.request_id)
            print(
                "Response headers:",
                {
                    key: exc.response.headers.get(key)
                    for key in (
                        "retry-after",
                        "retry-after-ms",
                        "x-ratelimit-limit-requests",
                        "x-ratelimit-remaining-requests",
                        "x-ratelimit-reset-requests",
                    )
                    if exc.response.headers.get(key) is not None
                },
            )
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
    
    
    def _create_embeddings_with_retry(self, texts: list[str]):
        """Create embeddings with bounded retries for Azure 429 responses.

        Azure may return a Retry-After header or include the wait time in the
        error message. If neither is available, use a conservative 60-second
        cooldown for rate-limit responses.
        """
        max_attempts = 3

        for attempt in range(max_attempts):
            try:
                return self._client.embeddings.create(
                    model=self._model,
                    input=texts,
                )
            except RateLimitError as exc:
                if attempt == max_attempts - 1:
                    raise

                headers = exc.response.headers
                delays: list[float] = []

                retry_after = headers.get("retry-after")
                if retry_after:
                    try:
                        delays.append(max(0.0, float(retry_after)))
                    except (TypeError, ValueError):
                        pass

                retry_after_ms = headers.get("retry-after-ms")
                if retry_after_ms:
                    try:
                        delays.append(max(0.0, float(retry_after_ms) / 1000.0))
                    except (TypeError, ValueError):
                        pass

                match = re.search(
                    r"retry after (\d+(?:\.\d+)?) seconds",
                    str(exc),
                    re.IGNORECASE,
                )
                if match:
                    delays.append(float(match.group(1)))

                # Azure's message in this incident explicitly requested 60 sec.
                # Use 60 sec as a fallback and never retry sooner than a supplied
                # server wait time. Small jitter helps avoid synchronized retries.
                wait_seconds = max(delays) if delays else 60.0
                time.sleep(wait_seconds + random.uniform(0.0, 1.0))

        raise RuntimeError("Embedding retries exhausted.")
