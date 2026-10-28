import time
from abc import ABC, abstractmethod
from typing import Sequence

from openai import OpenAI


class EmbeddingServiceError(RuntimeError):
    pass


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        raise NotImplementedError


class OpenAIEmbeddingService(EmbeddingProvider):
    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        timeout_seconds: float = 30,
        max_retries: int = 3,
    ) -> None:
        if not api_key:
            raise EmbeddingServiceError(
                "Set OPENAI_API_KEY before generating embeddings."
            )
        if not model:
            raise EmbeddingServiceError("OPENAI_EMBEDDING_MODEL is required.")
        self.model = model
        self.max_retries = max_retries
        self._client = OpenAI(api_key=api_key, timeout=timeout_seconds)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        cleaned = [text.strip() for text in texts]
        if any(not text for text in cleaned):
            raise EmbeddingServiceError("Embedding input contains empty text.")
        if len(cleaned) > 2048:
            raise EmbeddingServiceError("Embedding batch cannot exceed 2048 inputs.")

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self._client.embeddings.create(
                    model=self.model,
                    input=list(cleaned),
                )
                vectors = [item.embedding for item in response.data]
                if len(vectors) != len(cleaned):
                    raise EmbeddingServiceError(
                        "Embedding provider returned a response count that does not match the input."
                    )
                if any(len(vector) == 0 for vector in vectors):
                    raise EmbeddingServiceError("Embedding provider returned an empty vector.")
                dimension = len(vectors[0])
                if any(len(vector) != dimension for vector in vectors):
                    raise EmbeddingServiceError("Embedding provider returned inconsistent vector dimensions.")
                return vectors
            except EmbeddingServiceError:
                raise
            except Exception as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                time.sleep(min(0.25 * (2 ** attempt), 2.0))

        raise EmbeddingServiceError(
            "Embedding generation failed due to a provider or network error."
        ) from last_error


class DeterministicEmbeddingService(EmbeddingProvider):
    """Small deterministic provider for tests and local development checks."""

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        import hashlib
        vectors: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.strip().encode("utf-8")).digest()
            vectors.append([((byte % 31) - 15) / 15 for byte in digest[:32]])
        return vectors
