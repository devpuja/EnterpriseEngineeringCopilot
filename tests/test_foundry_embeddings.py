
# import asyncio
# import os

# from dotenv import load_dotenv
# from azure.identity.aio import AzureCliCredential
# from agent_framework.foundry import FoundryEmbeddingClient

# load_dotenv()


# async def main():
#     endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
#     model = os.environ["FOUNDRY_EMBEDDING_MODEL"]

#     texts = [
#         "CAP theorem describes consistency, availability, and partition tolerance.",
#         "Azure AI Search supports retrieving relevant engineering documents.",
#     ]

#     async with AzureCliCredential() as credential:
#         async with FoundryEmbeddingClient(
#             project_endpoint=endpoint,
#             model=model,
#             credential=credential,
#         ) as client:
#             embeddings = await client.get_embeddings(texts)

#             print(f"Number of embeddings: {len(embeddings)}")
#             print(f"Vector dimensions: {embeddings[0].dimensions}")
#             print(f"First vector length: {len(embeddings[0].vector)}")


# if __name__ == "__main__":
#     asyncio.run(main())




from openai import OpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

endpoint = (
    "https://enterprise-engineering-copilot-foundry"
    ".openai.azure.com/openai/v1/"
)

credential = DefaultAzureCredential()

token_provider = get_bearer_token_provider(
    credential,
    "https://ai.azure.com/.default",
)

client = OpenAI(
    base_url=endpoint,
    api_key=token_provider,
)

response = client.embeddings.create(
    model="text-embedding-3-small",
    input="Testing embeddings for Enterprise Engineering Copilot.",
)

print("Embedding dimensions:", len(response.data[0].embedding))
