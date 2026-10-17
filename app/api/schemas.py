
from pydantic import BaseModel, Field


class ArchitectureRequest(BaseModel):
    requirements: str = Field(
        min_length=10,
        max_length=12000,
        description="Business and technical requirements for the architecture.",
        examples=[
            "Design a multi-tenant document processing system "
            "that processes PDFs asynchronously."
        ],
    )


class ArchitectureResponse(BaseModel):
    agent: str
    model_provider: str
    recommendation: str