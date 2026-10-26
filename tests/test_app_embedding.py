from app.config.settings import settings
from app.rag.embeddings import FoundryEmbeddingProvider


print("RAG backend:", settings.rag_backend)
print("Embedding endpoint:", settings.foundry_openai_endpoint)
print("Embedding model:", settings.foundry_embedding_model)

provider = FoundryEmbeddingProvider()
vector = provider.embed(
    "Testing embeddings through the application's RAG provider."
)

print("SUCCESS — embedding dimensions:", len(vector))