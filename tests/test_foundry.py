
import asyncio
import os

from dotenv import load_dotenv
from azure.identity.aio import AzureCliCredential
from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient

load_dotenv()


async def main():
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    model = os.environ["FOUNDRY_MODEL"]

    async with AzureCliCredential() as credential:
        agent = Agent(
            client=FoundryChatClient(
                project_endpoint=endpoint,
                model=model,
                credential=credential,
            ),
            name="FoundryConnectionTest",
            instructions="Answer briefly and clearly.",
        )

        result = await agent.run(
            "Reply with: Microsoft Foundry connection successful."
        )
        print(result)


if __name__ == "__main__":
    asyncio.run(main())
