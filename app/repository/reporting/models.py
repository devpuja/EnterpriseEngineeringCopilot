from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, PrivateAttr

from app.repository.analysis.models import EvidenceReference
from app.repository.review.models import ArchitectureReviewResult
from app.repository.synthesis.models import ArchitectureSynthesisResult
from app.repository.visualization.models import ArchitectureDiagram


class ReportFormat(str, Enum):
    markdown = "markdown"
    html = "html"
    pdf = "pdf"
    docx = "docx"


class ReportConfiguration(BaseModel):
    title: str | None = None
    selected_diagram_types: list[str] = Field(default_factory=list)
    include_sections: list[str] = Field(default_factory=list)
    exclude_sections: list[str] = Field(default_factory=list)
    include_evidence: bool = Field(default=True, exclude=True)
    include_confidence: bool = Field(default=True, exclude=True)
    include_limitations: bool = Field(default=True, exclude=True)
    include_mermaid_source: bool = Field(default=True, exclude=True)
    include_rendered_diagrams: bool = Field(default=True, exclude=True)
    output_format: ReportFormat = ReportFormat.markdown
    organization_name: str | None = None
    project_name: str | None = None
    report_version: str = "1.0"
    maximum_diagram_nodes: int = Field(default=30, ge=1)


class ReportSection(BaseModel):
    section_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    content: str
    evidence_references: list[str] = Field(default_factory=list)
    related_diagram_ids: list[str] = Field(default_factory=list)


class ReportMetadata(BaseModel):
    generated_at: str
    report_version: str = "1.0"
    analysis_date: str | None = None
    organization_name: str | None = None
    project_name: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class ArchitectureReport(BaseModel):
    report_id: UUID = Field(default_factory=uuid4)
    analysis_id: UUID
    repository_name: str = Field(min_length=1)
    repository_source_type: str = "unknown"
    repository_reference: str = ""
    synthesis_id: UUID | None = None
    review_id: UUID | None = None
    title: str = Field(min_length=1)
    sections: list[ReportSection] = Field(default_factory=lambda: list[ReportSection]())
    diagrams: list[ArchitectureDiagram] = Field(default_factory=lambda: list[ArchitectureDiagram]())
    evidence: list[EvidenceReference] = Field(default_factory=list)
    synthesis: ArchitectureSynthesisResult | None = None
    review: ArchitectureReviewResult | None = None
    report_metadata: ReportMetadata
    limitations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    configuration: ReportConfiguration = Field(default_factory=ReportConfiguration)
    validated: bool = False
    _source_repository_root: str | None = PrivateAttr(default=None)


class ReportExportResult(BaseModel):
    report_id: UUID
    output_format: ReportFormat
    output_file_name: str = Field(min_length=1)
    managed_artifact_reference: str | None = None
    output_location: str | None = Field(
        default=None,
        description="Managed relative location; never an internal absolute path.",
    )
    file_size: int = Field(default=0, ge=0)
    mime_type: str | None = None
    export_status: str
    warnings: list[str] = Field(default_factory=list)
