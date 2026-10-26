from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import OpenAI, APIStatusError

endpoint = (
    "https://enterprise-engineering-copilot-foundry.openai.azure.com/openai/v1/"
)
model = "text-embedding-3-small"

scopes = [
    "https://ai.azure.com/.default",
    "https://cognitiveservices.azure.com/.default",
]

credential = DefaultAzureCredential()

try:
    for scope in scopes:
        print(f"\nTesting scope: {scope}")

        client = OpenAI(
            base_url=endpoint,
            api_key=get_bearer_token_provider(credential, scope),
            max_retries=0,
        )

        try:
            response = client.embeddings.create(
                model=model,
                input="Testing embeddings for Enterprise Engineering Copilot.",
            )
            print("SUCCESS — dimensions:", len(response.data[0].embedding))
        except APIStatusError as exc:
            print("FAILED — status:", exc.status_code)
            print("Error:", str(exc))
        finally:
            client.close()
finally:
    credential.close()