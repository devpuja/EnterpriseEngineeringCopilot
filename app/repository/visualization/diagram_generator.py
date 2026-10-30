import hashlib
import html
import re
from typing import Iterable

from app.repository.analysis.models import (
    RepositoryAnalysisResult,
    ConfidenceLevel,
)
from app.repository.visualization.diagram_layout import DiagramLayout
from app.repository.visualization.evidence_mapper import EvidenceMapper
from app.repository.visualization.models import (
    ArchitectureDiagram,
    DiagramNode,
    DiagramRelationship,
    DiagramType,
)


class DiagramGenerator:
    def __init__(self, evidence_mapper: EvidenceMapper | None = None, maximum_nodes: int = 30):
        self.evidence_mapper = evidence_mapper or EvidenceMapper()
        self.layout = DiagramLayout(maximum_nodes)

    def _stable_id(self, prefix: str, value: str, index: int) -> str:
        digest = hashlib.sha1(f"{prefix}:{value}:{index}".encode("utf-8")).hexdigest()[:8]
        return f"{prefix}_{digest}"

    def _label(self, value: str) -> str:
        value = re.sub(r"<[^>]*>", "", value)
        value = html.escape(value, quote=True)
        value = value.replace('"', "&quot;").replace("[", "&#91;").replace("]", "&#93;")
        value = re.sub(r"[\r\n\t]+", " ", value).strip()
        return value[:160] or "Unknown"

    def _limited(
        self,
        source: str,
        items: Iterable[object],
        warning_prefix: str,
    ) -> tuple[list[object], str | None]:
        item_list = list(items)
        limited, truncated = self.layout.limit_items(item_list)
        warning = f"{warning_prefix}: diagram limited to the first {self.layout.maximum_nodes} items." if truncated else None
        return limited, warning

    def generate(self, analysis: RepositoryAnalysisResult) -> list[ArchitectureDiagram]:
        diagrams: list[ArchitectureDiagram] = []
        diagrams.append(self._system_context(analysis))
        diagrams.append(self._component(analysis))
        diagrams.append(self._dependencies(analysis))
        diagrams.append(self._api(analysis))
        diagrams.append(self._database(analysis))
        diagrams.append(self._integrations(analysis))
        diagrams.append(self._patterns(analysis))
        return diagrams

    def _system_context(self, analysis: RepositoryAnalysisResult) -> ArchitectureDiagram:
        app_id = "application"
        nodes = [DiagramNode(
            node_id=app_id,
            label=self._label(analysis.repository_name),
            origin="Repository metadata from RepositoryAnalysisResult",
        )]
        relationships: list[DiagramRelationship] = []
        node_refs: dict[str, list[str]] = {}
        relation_refs: dict[str, list[str]] = {}
        items, warning = self._limited("system", analysis.projects, "System context projects were truncated")
        lines = [f'flowchart LR\n    {app_id}["{self._label(analysis.repository_name)}"]']
        for index, project in enumerate(items):
            node_id = self._stable_id("project", project.name, index)
            evidence = self.evidence_mapper.map_evidence(analysis, project.evidence_references, f"project:{project.name}")
            nodes.append(DiagramNode(node_id=node_id, label=self._label(project.name), evidence_references=evidence))
            node_refs[node_id] = project.evidence_references
            relationship = DiagramRelationship(
                source_node_id=app_id,
                target_node_id=node_id,
                relationship_type="contains",
                label="contains",
                evidence_references=evidence,
            )
            relationships.append(relationship)
            relation_refs[f"{app_id}->{node_id}"] = project.evidence_references
            lines.append(f'    {app_id} -->|contains| {node_id}["{self._label(project.name)}"]')

        database_items = analysis.database_findings[:self.layout.maximum_nodes]
        for index, database in enumerate(database_items):
            node_id = self._stable_id("database", database.technology, index)
            evidence = self.evidence_mapper.map_evidence(analysis, database.evidence_references, f"database:{database.technology}")
            nodes.append(DiagramNode(node_id=node_id, label=self._label(database.technology), evidence_references=evidence))
            relationship = DiagramRelationship(
                source_node_id=app_id, target_node_id=node_id,
                relationship_type="persists_data_with", label="persists data with",
                evidence_references=evidence,
            )
            relationships.append(relationship)
            node_refs[node_id] = database.evidence_references
            relation_refs[f"{app_id}->{node_id}"] = database.evidence_references
            lines.append(f'    {app_id} -->|persists data with| {node_id}["{self._label(database.technology)}"]')

        integration_items = [
            item for item in analysis.external_integrations
            if item.status.lower() == "confirmed"
        ][:self.layout.maximum_nodes]
        for index, integration in enumerate(integration_items):
            node_id = self._stable_id("external", integration.name, index)
            evidence = self.evidence_mapper.map_evidence(analysis, integration.evidence_references, f"integration:{integration.name}")
            nodes.append(DiagramNode(node_id=node_id, label=self._label(integration.name), evidence_references=evidence))
            relationships.append(DiagramRelationship(
                source_node_id=app_id, target_node_id=node_id,
                relationship_type="integrates_with", label="integrates with",
                evidence_references=evidence,
            ))
            node_refs[node_id] = integration.evidence_references
            relation_refs[f"{app_id}->{node_id}"] = integration.evidence_references
            lines.append(f'    {app_id} -->|integrates with| {node_id}["{self._label(integration.name)}"]')

        evidence_ids = sorted({
            evidence_id
            for node in nodes
            for evidence in node.evidence_references
            if (evidence_id := evidence.evidence_id)
        })
        return ArchitectureDiagram(
            diagram_id="system_context",
            title="System Context",
            diagram_type=DiagramType.system_context,
            description="High-level system view derived only from repository analysis findings.",
            mermaid_source="\n".join(lines),
            nodes=nodes,
            relationships=relationships,
            evidence_references=evidence_ids,
            evidence_map=self.evidence_mapper.evidence_map(analysis, node_refs, relation_refs),
            generation_warnings=[warning] if warning else [],
        )

    def _component(self, analysis: RepositoryAnalysisResult) -> ArchitectureDiagram:
        app_id = "application"
        lines = [f'flowchart LR\n    {app_id}["{self._label(analysis.repository_name)}"]']
        nodes = [DiagramNode(node_id=app_id, label=self._label(analysis.repository_name), origin="Repository metadata")]
        relationships: list[DiagramRelationship] = []
        node_refs: dict[str, list[str]] = {}
        relation_refs: dict[str, list[str]] = {}

        component_items: list[object] = list(analysis.projects)
        component_items.extend(analysis.technology_stack)
        limited, warning = self.layout.limit_items(component_items)
        for index, item in enumerate(limited):
            name = getattr(item, "name", "")
            evidence_ids = getattr(item, "evidence_references", [])
            node_id = self._stable_id("component", name, index)
            evidence = self.evidence_mapper.map_evidence(analysis, evidence_ids, f"component:{name}")
            nodes.append(DiagramNode(node_id=node_id, label=self._label(name), evidence_references=evidence))
            relationships.append(DiagramRelationship(
                source_node_id=app_id, target_node_id=node_id,
                relationship_type="contains", label="contains",
                evidence_references=evidence,
            ))
            node_refs[node_id] = evidence_ids
            relation_refs[f"{app_id}->{node_id}"] = evidence_ids
            lines.append(f'    {app_id} -->|contains| {node_id}["{self._label(name)}"]')

        evidence_ids = sorted({e.evidence_id for node in nodes for e in node.evidence_references})
        return ArchitectureDiagram(
            diagram_id="component_architecture",
            title="Component Architecture",
            diagram_type=DiagramType.component,
            description="Major projects and technologies represented as components when supported by analysis evidence.",
            mermaid_source="\n".join(lines),
            nodes=nodes,
            relationships=relationships,
            evidence_references=evidence_ids,
            evidence_map=self.evidence_mapper.evidence_map(analysis, node_refs, relation_refs),
            generation_warnings=[
                "Diagram limited to the first 30 component or technology findings."
            ] if warning else [],
        )

    def _dependencies(self, analysis: RepositoryAnalysisResult) -> ArchitectureDiagram:
        lines = ["flowchart LR"]
        nodes: list[DiagramNode] = []
        relationships: list[DiagramRelationship] = []
        node_refs: dict[str, list[str]] = {}
        relation_refs: dict[str, list[str]] = {}
        limited, warning = self.layout.limit_items(analysis.dependencies)
        for index, dependency in enumerate(limited):
            source_id = self._stable_id("source", dependency.source, index)
            target_id = self._stable_id("target", dependency.target, index)
            source_refs = self.evidence_mapper.map_evidence(analysis, dependency.evidence_references, f"dependency:{dependency.source}")
            target_refs = self.evidence_mapper.map_evidence(analysis, dependency.evidence_references, f"dependency:{dependency.target}")
            for node_id, label, refs in (
                (source_id, dependency.source, source_refs),
                (target_id, dependency.target, target_refs),
            ):
                if node_id not in {node.node_id for node in nodes}:
                    nodes.append(DiagramNode(node_id=node_id, label=self._label(label), evidence_references=refs))
                    node_refs[node_id] = dependency.evidence_references
                    lines.append(f'    {node_id}["{self._label(label)}"]')
            relationship_type = dependency.dependency_type
            evidence = self.evidence_mapper.map_evidence(
                analysis, dependency.evidence_references,
                f"dependency:{dependency.source}->{dependency.target}",
            )
            relationships.append(DiagramRelationship(
                source_node_id=source_id,
                target_node_id=target_id,
                relationship_type=relationship_type,
                label=relationship_type if relationship_type else None,
                evidence_references=evidence,
            ))
            relation_refs[f"{source_id}->{target_id}"] = dependency.evidence_references
            lines.append(
                f'    {source_id} -->|{self._label(relationship_type or "depends on")}| {target_id}'
            )
        if not relationships:
            nodes = [DiagramNode(node_id="no_dependencies", label="No supported dependency findings")]
            lines.append('    no_dependencies["No supported dependency findings"]')
        evidence_ids = sorted({e.evidence_id for node in nodes for e in node.evidence_references})
        return ArchitectureDiagram(
            diagram_id="project_dependencies",
            title="Project and Dependency Relationships",
            diagram_type=DiagramType.dependency,
            description="Dependency relationships confirmed by static Milestone 2 findings.",
            mermaid_source="\n".join(lines),
            nodes=nodes,
            relationships=relationships,
            evidence_references=evidence_ids,
            evidence_map=self.evidence_mapper.evidence_map(analysis, node_refs, relation_refs),
            generation_warnings=["No supported dependency findings were identified."] if not relationships else (
                ["Diagram limited to the first 30 dependency findings."] if warning else []
            ),
        )

    def _api(self, analysis: RepositoryAnalysisResult) -> ArchitectureDiagram:
        lines = ["flowchart LR"]
        nodes: list[DiagramNode] = []
        relationships: list[DiagramRelationship] = []
        node_refs: dict[str, list[str]] = {}
        relation_refs: dict[str, list[str]] = {}
        limited, warning = self.layout.limit_items(analysis.api_endpoints)

        app_id = "repository"
        app_node = DiagramNode(node_id=app_id, label=self._label(analysis.repository_name), origin="Repository metadata")
        nodes.append(app_node)
        lines.append(f'    {app_id}["{self._label(analysis.repository_name)}"]')

        for index, endpoint in enumerate(limited):
            exposure = (endpoint.exposure or "unknown").lower()
            route = endpoint.route or "Unknown route"
            label = f"{endpoint.method} {route}" if endpoint.method else route
            prefix = "exposed_api" if exposure == "exposed" else "consumed_api" if exposure == "consumed" else "api_finding"
            node_id = self._stable_id(prefix, label, index)
            evidence = self.evidence_mapper.map_evidence(
                analysis, endpoint.evidence_references,
                f"api:{endpoint.method}:{route}",
            )
            nodes.append(DiagramNode(node_id=node_id, label=self._label(label), evidence_references=evidence))
            node_refs[node_id] = endpoint.evidence_references
            source_id, target_id, relation_type = (
                (app_id, node_id, "exposes") if exposure == "exposed"
                else (node_id, app_id, "consumes") if exposure == "consumed"
                else (app_id, node_id, "api_finding")
            )
            relationships.append(DiagramRelationship(
                source_node_id=source_id,
                target_node_id=target_id,
                relationship_type=relation_type,
                label=relation_type,
                evidence_references=evidence,
            ))
            relation_refs[f"{source_id}->{target_id}"] = endpoint.evidence_references
            lines.append(f'    {source_id} -->|{relation_type}| {node_id}["{self._label(label)}"]')

        if not limited:
            nodes.append(DiagramNode(node_id="no_api_findings", label="No supported API findings"))
            lines.append('    no_api_findings["No supported API findings"]')

        evidence_ids = sorted({e.evidence_id for node in nodes for e in node.evidence_references})
        return ArchitectureDiagram(
            diagram_id="api_architecture",
            title="API Architecture",
            diagram_type=DiagramType.api,
            description="Exposed and consumed API findings distinguished using Milestone 2 evidence.",
            mermaid_source="\n".join(lines),
            nodes=nodes,
            relationships=relationships,
            evidence_references=evidence_ids,
            evidence_map=self.evidence_mapper.evidence_map(analysis, node_refs, relation_refs),
            generation_warnings=(
                ["No supported API findings were identified."]
                if not limited else
                ["Diagram limited to the first 30 API findings."] if warning else []
            ),
        )

    def _database(self, analysis: RepositoryAnalysisResult) -> ArchitectureDiagram:
        app_id = "application"
        lines = [f'flowchart LR\n    {app_id}["{self._label(analysis.repository_name)}"]']
        nodes = [DiagramNode(node_id=app_id, label=self._label(analysis.repository_name), origin="Repository metadata")]
        relationships: list[DiagramRelationship] = []
        node_refs: dict[str, list[str]] = {}
        relation_refs: dict[str, list[str]] = {}
        limited, warning = self.layout.limit_items(analysis.database_findings)
        for index, finding in enumerate(limited):
            node_id = self._stable_id("persistence", finding.technology, index)
            evidence = self.evidence_mapper.map_evidence(
                analysis, finding.evidence_references,
                f"database:{finding.technology}",
            )
            nodes.append(DiagramNode(node_id=node_id, label=self._label(finding.technology), evidence_references=evidence))
            relationships.append(DiagramRelationship(
                source_node_id=app_id,
                target_node_id=node_id,
                relationship_type=finding.evidence_type or "persistence",
                label=finding.evidence_type or "persistence",
                evidence_references=evidence,
            ))
            node_refs[node_id] = finding.evidence_references
            relation_refs[f"{app_id}->{node_id}"] = finding.evidence_references
            lines.append(
                f'    {app_id} -->|{self._label(finding.evidence_type or "persistence")}| '
                f'{node_id}["{self._label(finding.technology)}"]'
            )
        if not limited:
            nodes.append(DiagramNode(node_id="no_persistence", label="No supported persistence findings"))
            lines.append('    no_persistence["No supported persistence findings"]')
        evidence_ids = sorted({e.evidence_id for node in nodes for e in node.evidence_references})
        return ArchitectureDiagram(
            diagram_id="database_architecture",
            title="Database and Persistence Architecture",
            diagram_type=DiagramType.database,
            description="Persistence technologies and components identified by static repository evidence.",
            mermaid_source="\n".join(lines),
            nodes=nodes,
            relationships=relationships,
            evidence_references=evidence_ids,
            evidence_map=self.evidence_mapper.evidence_map(analysis, node_refs, relation_refs),
            generation_warnings=(
                ["No supported database or persistence findings were identified."]
                if not limited else
                ["Diagram limited to the first 30 persistence findings."] if warning else []
            ),
        )

    def _integrations(self, analysis: RepositoryAnalysisResult) -> ArchitectureDiagram:
        app_id = "application"
        lines = [f'flowchart LR\n    {app_id}["{self._label(analysis.repository_name)}"]']
        nodes = [DiagramNode(node_id=app_id, label=self._label(analysis.repository_name), origin="Repository metadata")]
        relationships: list[DiagramRelationship] = []
        node_refs: dict[str, list[str]] = {}
        relation_refs: dict[str, list[str]] = {}
        limited, warning = self.layout.limit_items(analysis.external_integrations)
        for index, finding in enumerate(limited):
            node_id = self._stable_id("integration", finding.name, index)
            evidence = self.evidence_mapper.map_evidence(
                analysis, finding.evidence_references,
                f"integration:{finding.name}",
            )
            status_label = finding.status.lower().replace("_", " ")
            nodes.append(DiagramNode(node_id=node_id, label=self._label(finding.name), evidence_references=evidence))
            relationships.append(DiagramRelationship(
                source_node_id=app_id,
                target_node_id=node_id,
                relationship_type=finding.integration_type,
                label=f"{finding.integration_type} ({status_label})",
                evidence_references=evidence,
            ))
            node_refs[node_id] = finding.evidence_references
            relation_refs[f"{app_id}->{node_id}"] = finding.evidence_references
            lines.append(
                f'    {app_id} -->|{self._label(finding.integration_type + " (" + status_label + ")")}| '
                f'{node_id}["{self._label(finding.name)}"]'
            )
        if not limited:
            nodes.append(DiagramNode(node_id="no_integrations", label="No supported external integrations"))
            lines.append('    no_integrations["No supported external integrations"]')
        evidence_ids = sorted({e.evidence_id for node in nodes for e in node.evidence_references})
        return ArchitectureDiagram(
            diagram_id="external_integrations",
            title="External Integration Architecture",
            diagram_type=DiagramType.integration,
            description="External integrations with confirmed, declared, or inferred status preserved from analysis.",
            mermaid_source="\n".join(lines),
            nodes=nodes,
            relationships=relationships,
            evidence_references=evidence_ids,
            evidence_map=self.evidence_mapper.evidence_map(analysis, node_refs, relation_refs),
            generation_warnings=(
                ["No supported external integration findings were identified."]
                if not limited else
                ["Diagram limited to the first 30 integration findings."] if warning else []
            ),
        )

    def _patterns(self, analysis: RepositoryAnalysisResult) -> ArchitectureDiagram:
        app_id = "application"
        lines = [f'flowchart LR\n    {app_id}["{self._label(analysis.repository_name)}"]']
        nodes = [DiagramNode(node_id=app_id, label=self._label(analysis.repository_name), origin="Repository metadata")]
        relationships: list[DiagramRelationship] = []
        node_refs: dict[str, list[str]] = {}
        relation_refs: dict[str, list[str]] = {}
        supported = [
            pattern for pattern in analysis.architectural_patterns
            if pattern.name.lower() != "not determined"
            and pattern.confidence != ConfidenceLevel.low
            and (pattern.evidence or pattern.relevant_files)
        ]
        limited, warning = self.layout.limit_items(supported)
        for index, pattern in enumerate(limited):
            node_id = self._stable_id("pattern", pattern.name, index)
            evidence = self.evidence_mapper.map_paths(
                analysis,
                pattern.relevant_files,
                f"pattern:{pattern.name}",
            )
            ids = [item.evidence_id for item in evidence]
            nodes.append(DiagramNode(node_id=node_id, label=self._label(pattern.name), evidence_references=evidence))
            relationships.append(DiagramRelationship(
                source_node_id=app_id,
                target_node_id=node_id,
                relationship_type="uses_pattern",
                label=f"{pattern.confidence.value} confidence",
                evidence_references=evidence,
            ))
            node_refs[node_id] = ids
            relation_refs[f"{app_id}->{node_id}"] = ids
            lines.append(
                f'    {app_id} -->|{pattern.confidence.value} confidence| '
                f'{node_id}["{self._label(pattern.name)}"]'
            )
        if not limited:
            nodes.append(DiagramNode(node_id="pattern_not_determined", label="Architecture pattern not determined"))
            lines.append('    pattern_not_determined["Architecture pattern not determined"]')
        evidence_ids = sorted({e.evidence_id for node in nodes for e in node.evidence_references})
        return ArchitectureDiagram(
            diagram_id="architecture_patterns",
            title="Architecture Patterns",
            diagram_type=DiagramType.architecture_pattern,
            description="Only patterns with sufficient supporting Milestone 2 evidence are represented.",
            mermaid_source="\n".join(lines),
            nodes=nodes,
            relationships=relationships,
            evidence_references=evidence_ids,
            evidence_map=self.evidence_mapper.evidence_map(analysis, node_refs, relation_refs),
            generation_warnings=(
                ["No sufficiently supported architecture pattern was identified."]
                if not limited else
                ["Diagram limited to the first 30 pattern findings."] if warning else []
            ),
        )
