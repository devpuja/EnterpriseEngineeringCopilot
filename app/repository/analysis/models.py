from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ConfidenceLevel(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class EvidenceCategory(str, Enum):
    technology = "technology"
    project = "project"
    dependency = "dependency"
    api = "api"
    database = "database"
    integration = "integration"
    pattern = "pattern"
    entry_point = "entry_point"


class EvidenceReference(BaseModel):
    evidence_id: str
    relative_path: str
    category: EvidenceCategory
    explanation: str
    symbol: str | None = None
    line_number: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    confidence: ConfidenceLevel = ConfidenceLevel.high


class TechnologyFinding(BaseModel):
    name: str
    category: str
    evidence_references: list[str] = Field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.medium


class ProjectFinding(BaseModel):
    name: str
    relative_path: str
    kind: str
    evidence_references: list[str] = Field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.medium


class EntryPointFinding(BaseModel):
    relative_path: str
    entry_point_type: str
    symbol: str | None = None
    evidence_references: list[str] = Field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.medium


class DependencyFinding(BaseModel):
    source: str
    target: str
    dependency_type: str
    resolved: bool
    evidence_references: list[str] = Field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.medium


class ApiEndpointFinding(BaseModel):
    exposure: str
    method: str
    route: str
    relative_path: str
    framework: str
    symbol: str | None = None
    evidence_references: list[str] = Field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.medium


class DatabaseFinding(BaseModel):
    technology: str
    evidence_type: str
    relative_path: str
    detail: str
    evidence_references: list[str] = Field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.medium


class IntegrationFinding(BaseModel):
    name: str
    integration_type: str
    status: str = "confirmed"
    relative_path: str | None = None
    detail: str
    evidence_references: list[str] = Field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.medium


class ArchitecturePatternFinding(BaseModel):
    name: str
    evidence: list[str] = Field(default_factory=list)
    relevant_files: list[str] = Field(default_factory=list)
    explanation: str
    confidence: ConfidenceLevel
    limitations: str


class ProjectStructureFinding(BaseModel):
    source_directories: list[str] = Field(default_factory=list)
    test_directories: list[str] = Field(default_factory=list)
    config_locations: list[str] = Field(default_factory=list)
    infrastructure_locations: list[str] = Field(default_factory=list)
    shared_libraries: list[str] = Field(default_factory=list)
    summary: str


class RepositoryAnalysisResult(BaseModel):
    analysis_id: UUID = Field(default_factory=uuid4)
    repository_name: str
    source_type: str
    source_reference: str
    technology_stack: list[TechnologyFinding] = Field(default_factory=list)
    projects: list[ProjectFinding] = Field(default_factory=list)
    application_entry_points: list[EntryPointFinding] = Field(default_factory=list)
    project_structure: ProjectStructureFinding
    dependencies: list[DependencyFinding] = Field(default_factory=list)
    api_endpoints: list[ApiEndpointFinding] = Field(default_factory=list)
    database_findings: list[DatabaseFinding] = Field(default_factory=list)
    external_integrations: list[IntegrationFinding] = Field(default_factory=list)
    architectural_patterns: list[ArchitecturePatternFinding] = Field(default_factory=list)
    evidence: list[EvidenceReference] = Field(default_factory=list)
    analysis_warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    summary: str
