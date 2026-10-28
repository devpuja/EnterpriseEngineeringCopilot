
from pydantic import BaseModel, Field
from typing import Literal 


class ArchitectureReviewFinding(BaseModel):
    severity: Literal["critical", "high", "medium", "low"]
    category: Literal[
        "security",
        "reliability",
        "consistency",
        "scalability",
        "maintainability",
        "data_flow",
        "cost",
    ]
    finding: str
    evidence: str
    recommendation: str


class ArchitectureReview(BaseModel):
    summary: str
    findings: list[ArchitectureReviewFinding]
    approval_recommendation: Literal[
        "approve",
        "revise",
        "needs_human_review",
    ]

    
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
    constraints: list[str] = Field(default_factory=list)


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
    review: ArchitectureReview | None = None


class IndexedDocument(BaseModel):
    document_id: str
    filename: str
    media_type: str
    size_bytes: int
    chunk_count: int
    status: Literal["indexed", "failed"]
    error: str | None = None
    created_at: str
    updated_at: str


class RAGSource(BaseModel):
    document_id: str
    filename: str
    chunk_index: int
    page_number: int | None = None
    excerpt: str


class RAGQuery(BaseModel):
    question: str = Field(min_length=3, max_length=4000)
    top_k: int | None = Field(default=None, ge=1, le=20)


class RAGAnswer(BaseModel):
    answer: str
    grounded: bool
    sources: list[RAGSource]
    document_ids: list[str] = Field(default_factory=list)


class GeneratedRAGAnswer(BaseModel):
    answer: str
    grounded: bool