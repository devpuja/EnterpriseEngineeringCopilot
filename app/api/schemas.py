
from pydantic import BaseModel, Field


class ArchitectureRequest(BaseModel):
    requirements: str = Field(
        min_length=10,
        max_length=12000,
        description="Business and technical architecture requirements.",
    )


class RequirementAnalysis(BaseModel):
    functional_requirements: list[str]
    non_functional_requirements: list[str]
    assumptions: list[str]
    open_questions: list[str]


class ArchitectureComponent(BaseModel):
    name: str
    responsibility: str
    technology: str
    rationale: str


class ArchitectureDecision(BaseModel):
    decision: str
    rationale: str
    alternatives: list[str]
    trade_offs: list[str]


class ArchitectureRisk(BaseModel):
    risk: str
    impact: str
    mitigation: str


class ArchitectureDesign(BaseModel):
    summary: str
    components: list[ArchitectureComponent]
    data_flow: list[str]
    mermaid_diagram: str


class ArchitectureResponse(BaseModel):
    agent: str
    model_provider: str
    requirements_analysis: RequirementAnalysis
    architecture: ArchitectureDesign
    decisions: list[ArchitectureDecision]
    risks: list[ArchitectureRisk]
    next_steps: list[str]