from app.repository.visualization.models import DiagramType


SUPPORTED_DIAGRAM_TYPES = tuple(item.value for item in DiagramType) + (
    "unified_architecture",
)

SECTION_ORDER = (
    "cover",
    "executive_summary",
    "repository_overview",
    "existing_architecture",
    "architecture_diagrams",
    "technology_stack",
    "components_dependencies",
    "api_architecture",
    "database_architecture",
    "external_integrations",
    "architecture_findings",
    "architecture_synthesis",
    "architecture_components",
    "architecture_relationships",
    "architecture_data_flows",
    "external_systems",
    "architecture_review",
    "review_findings",
    "architecture_strengths",
    "recommendations",
    "limitations",
    "evidence_references",
    "appendix",
)
