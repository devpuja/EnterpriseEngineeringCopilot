from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.repository.analysis.models import ConfidenceLevel


class ArchitectureReviewCategory(str, Enum):
    architecture_structure = "architecture_structure"
    dependencies_coupling = "dependencies_coupling"
    integration_architecture = "integration_architecture"
    data_flow = "data_flow"
    maintainability = "maintainability"
    reliability = "reliability"
    security = "security"
    scalability = "scalability"
    evidence_quality = "evidence_quality"


class ArchitectureReviewSeverity(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"
    informational = "informational"


class ArchitectureReviewFindingStatus(str, Enum):
    confirmed = "confirmed"
    inferred = "inferred"
    needs_investigation = "needs_investigation"


class ArchitectureReviewOutcome(str, Enum):
    healthy = "healthy"
    improvements_recommended = "improvements_recommended"
    needs_investigation = "needs_investigation"
    significant_risks = "significant_risks"


class ArchitectureReviewRecommendation(BaseModel):
    recommendation: str
    benefits: list[str] = Field(default_factory=list)
    trade_offs: list[str] = Field(default_factory=list)
    implementation_considerations: list[str] = Field(default_factory=list)
    priority: str = "medium"
    implementation_effort: str = "medium"


class ArchitectureReviewFinding(BaseModel):
    finding_id: str = Field(min_length=1)
    rule_id: str | None = None
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    category: ArchitectureReviewCategory
    severity: ArchitectureReviewSeverity
    status: ArchitectureReviewFindingStatus
    affected_component_ids: list[str] = Field(default_factory=list)
    related_relationships: list[str] = Field(default_factory=list)
    related_data_flows: list[str] = Field(default_factory=list)
    related_relationship_references: list[str] = Field(default_factory=list)
    related_data_flow_references: list[str] = Field(default_factory=list)
    evidence_references: list[str] = Field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.medium
    recommendation: str
    benefits: list[str] = Field(default_factory=list)
    trade_offs: list[str] = Field(default_factory=list)
    implementation_considerations: list[str] = Field(default_factory=list)


class ArchitectureReviewStrength(BaseModel):
    title: str
    description: str
    evidence_references: list[str] = Field(default_factory=list)
    affected_component_ids: list[str] = Field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.medium


class ArchitectureReviewResult(BaseModel):
    review_id: UUID = Field(default_factory=uuid4)
    original_synthesis_id: UUID
    original_analysis_id: UUID | None = None
    repository_name: str = Field(min_length=1)
    review_summary: str
    overall_review_outcome: ArchitectureReviewOutcome
    findings: list[ArchitectureReviewFinding] = Field(default_factory=list[ArchitectureReviewFinding])
    strengths: list[ArchitectureReviewStrength] = Field(default_factory=list[ArchitectureReviewStrength])
    priority_recommendations: list[ArchitectureReviewRecommendation] = Field(default_factory=list[ArchitectureReviewRecommendation])
    warnings: list[str] = Field(default_factory=list[str])
    limitations: list[str] = Field(default_factory=list[str])
    review_metadata: dict[str, Any] = Field(default_factory=dict)