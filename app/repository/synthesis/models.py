from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.repository.analysis.models import ConfidenceLevel
from app.repository.visualization.models import ArchitectureDiagram


class RelationshipStatus(str, Enum):
    confirmed = "confirmed"
    inferred = "inferred"


class ArchitectureComponent(BaseModel):
    component_id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    name: str = Field(min_length=1)
    component_type: str
    description: str
    project_references: list[str] = Field(default_factory=list)
    evidence_references: list[str] = Field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.medium


class ArchitectureRelationship(BaseModel):
    source_component_id: str
    target_component_id: str
    relationship_type: str
    description: str
    status: RelationshipStatus = RelationshipStatus.confirmed
    evidence_references: list[str] = Field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.medium


class ArchitectureDataFlow(BaseModel):
    source_component_id: str
    target_component_id: str
    flow_description: str
    interaction_type: str | None = None
    evidence_references: list[str] = Field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.medium
    status: RelationshipStatus = RelationshipStatus.confirmed


class ExternalSystem(BaseModel):
    external_system_id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    name: str = Field(min_length=1)
    integration_type: str
    description: str
    evidence_references: list[str] = Field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.medium
    status: RelationshipStatus = RelationshipStatus.confirmed


class ArchitectureSynthesisMetadata(BaseModel):
    synthesis_generated_at: str
    synthesis_version: str = "1"
    deterministic: bool = True
    maximum_components: int = Field(default=30, ge=1)
    maximum_relationships: int = Field(default=30, ge=1)
    options: dict[str, Any] = Field(default_factory=dict)


class ArchitectureSynthesisResult(BaseModel):
    synthesis_id: UUID = Field(default_factory=uuid4)
    original_analysis_id: UUID
    repository_name: str = Field(min_length=1)
    components: list[ArchitectureComponent] = Field(default_factory=list[ArchitectureComponent])
    relationships: list[ArchitectureRelationship] = Field(default_factory=list[ArchitectureRelationship])
    data_flows: list[ArchitectureDataFlow] = Field(default_factory=list[ArchitectureDataFlow])
    external_systems: list[ExternalSystem] = Field(default_factory=list[ExternalSystem])
    architecture_summary: str
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    synthesis_metadata: ArchitectureSynthesisMetadata
    unified_diagram: ArchitectureDiagram | None = None


ArchitectureSynthesisModel = ArchitectureSynthesisResult
