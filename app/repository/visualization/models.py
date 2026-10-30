from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from app.repository.analysis.models import ConfidenceLevel, EvidenceCategory


class DiagramType(str, Enum):
    system_context = "system_context"
    component = "component"
    dependency = "dependency"
    api = "api"
    database = "database"
    integration = "integration"
    architecture_pattern = "architecture_pattern"


class DiagramEvidenceReference(BaseModel):
    evidence_id: str
    relative_path: str
    category: EvidenceCategory
    confidence: ConfidenceLevel
    finding_id: str | None = None
    explanation: str | None = None
    symbol: str | None = None
    line_number: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)


class DiagramNode(BaseModel):
    node_id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    label: str = Field(min_length=1)
    origin: str = "Derived from analysis finding"
    evidence_references: list[DiagramEvidenceReference] = Field(default_factory=lambda: list[DiagramEvidenceReference]())


class DiagramRelationship(BaseModel):
    source_node_id: str
    target_node_id: str
    relationship_type: str = "uses"
    label: str | None = None
    evidence_references: list[DiagramEvidenceReference] = Field(default_factory=lambda: list[DiagramEvidenceReference]())


class DiagramEvidenceMap(BaseModel):
    nodes: dict[str, list[DiagramEvidenceReference]] = Field(default_factory=dict)
    relationships: dict[str, list[DiagramEvidenceReference]] = Field(default_factory=dict)


class ArchitectureDiagram(BaseModel):
    diagram_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    diagram_type: DiagramType
    description: str
    mermaid_source: str = Field(min_length=1)
    rendered_svg: str | None = None
    rendered_png: bytes | None = None
    nodes: list[DiagramNode] = Field(default_factory=lambda: list[DiagramNode]())
    relationships: list[DiagramRelationship] = Field(default_factory=lambda: list[DiagramRelationship]())
    evidence_references: list[str] = Field(default_factory=list)
    evidence_map: DiagramEvidenceMap = Field(default_factory=DiagramEvidenceMap)
    generation_warnings: list[str] = Field(default_factory=list)


class DiagramGenerationMetadata(BaseModel):
    generated_at: str
    renderer_name: str = "mermaid-source"
    deterministic: bool = True
    complexity_limit: int = Field(default=30, ge=1)
    options: dict[str, Any] = Field(default_factory=dict)


class ArchitectureVisualizationResult(BaseModel):
    result_id: UUID = Field(default_factory=uuid4)
    analysis_id: UUID
    repository_name: str = Field(min_length=1)
    diagrams: list[ArchitectureDiagram] = Field(default_factory=lambda: list[ArchitectureDiagram]())
    visualization_warnings: list[str] = Field(default_factory=list)
    generation_metadata: DiagramGenerationMetadata
