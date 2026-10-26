
from app.config.settings import settings
from app.rag.search_index import AzureAISearchIndex

index_name = settings.azure_search_index_name.strip()

print(f"Initializing Azure AI Search index: {index_name}")

# The existing adapter creates the configured index if it is missing.
AzureAISearchIndex()

print(f"Index initialization completed: {index_name}")
