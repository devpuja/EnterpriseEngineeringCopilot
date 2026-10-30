import hashlib
import html
import re
from datetime import datetime, timezone
from uuid import uuid4

from app.repository.analysis.models import (
    ConfidenceLevel,
    RepositoryAnalysisResult,
)
from app.repository.visualization.diagram_validator import DiagramValidator
from app.repository.visualization.evidence_mapper import EvidenceMapper
from app.repository.visualization.models import (
    ArchitectureVisualizationResult,
    ArchitectureDiagram,
    DiagramNode,
    DiagramRelationship,
    DiagramType,
)
from app.repository.synthesis.models import (
    ArchitectureComponent,
    ArchitectureDataFlow,
    ArchitectureRelationship,
    ArchitectureSynthesisMetadata,
    ArchitectureSynthesisResult,
    ExternalSystem,
    RelationshipStatus,
)


class ArchitectureSynthesizer:
    def __init__(self, maximum_nodes: int = 30, maximum_edges: int = 30):
        self.maximum_nodes = max(1, maximum_nodes)
        self.maximum_edges = max(1, maximum_edges)
        self.evidence_mapper = EvidenceMapper()
        self.validator = DiagramValidator(maximum_nodes=maximum_nodes, maximum_edges=maximum_edges)

    def _stable_id(self, prefix: str, name: str, index: int = 0) -> str:
        digest = hashlib.sha1(f"{prefix}:{name}:{index}".encode("utf-8")).hexdigest()[:8]
        return f"{prefix}_{digest}"

    def _label(self, value: str) -> str:
        value = re.sub(r"<[^>]*>", "", value)
        value = html.escape(value, quote=True)
        value = value.replace("[", "&#91;").replace("]", "&#93;")
        value = value.replace("{", "&#123;").replace("}", "&#125;")
        value = value.replace("|", "&#124;")
        value = re.sub(r"[\r\n\t]+", " ", value).strip()
        return value[:160] or "Unknown"

    def _confidence(self, analysis: RepositoryAnalysisResult, ids: list[str], fallback: ConfidenceLevel) -> ConfidenceLevel:
        if not ids:
            return fallback
        levels = {item.confidence for item in analysis.evidence if item.evidence_id in set(ids)}
        if ConfidenceLevel.high in levels:
            return ConfidenceLevel.high
        if ConfidenceLevel.medium in levels:
            return ConfidenceLevel.medium
        return fallback if not levels else ConfidenceLevel.low

    def synthesize(
        self,
        analysis: RepositoryAnalysisResult,
        visualization: ArchitectureVisualizationResult | None = None,
    ) -> ArchitectureSynthesisResult:
        warnings: list[str] = []
        warnings.extend(analysis.analysis_warnings)
        warnings.extend(analysis.limitations)
        if visualization is not None and visualization.analysis_id != analysis.analysis_id:
            warnings.append("Visualization result belongs to a different analysis and was not used.")
            visualization = None

        components: list[ArchitectureComponent] = []
        relationships: list[ArchitectureRelationship] = []
        data_flows: list[ArchitectureDataFlow] = []
        external_systems: list[ExternalSystem] = []

        root_refs = self._evidence_refs_for_paths(analysis, [project.relative_path for project in analysis.projects])
        root_id = self._stable_id("repository", analysis.repository_name)
        components.append(ArchitectureComponent(
            component_id=root_id,
            name=analysis.repository_name,
            component_type="repository",
            description="Repository application boundary represented by static analysis findings.",
            project_references=sorted({p.relative_path for p in analysis.projects}),
            evidence_references=root_refs,
            confidence=ConfidenceLevel.high if root_refs else ConfidenceLevel.low,
        ))

        project_ids: dict[str, str] = {}
        for index, project in enumerate(analysis.projects):
            cid = self._stable_id("project", project.name, index)
            project_ids[project.relative_path] = cid
            components.append(ArchitectureComponent(
                component_id=cid,
                name=project.name,
                component_type="project",
                description=f"Project/package identified from {project.relative_path}.",
                project_references=[project.relative_path],
                evidence_references=project.evidence_references,
                confidence=project.confidence,
            ))
            relationships.append(ArchitectureRelationship(
                source_component_id=root_id,
                target_component_id=cid,
                relationship_type="contains",
                description="The repository contains this project/package.",
                status=RelationshipStatus.confirmed,
                evidence_references=project.evidence_references,
                confidence=project.confidence,
            ))

        for index, entry in enumerate(analysis.application_entry_points):
            cid = self._stable_id("entrypoint", entry.relative_path, index)
            components.append(ArchitectureComponent(
                component_id=cid,
                name=f"{entry.entry_point_type} entry point",
                component_type="entry_point",
                description=f"Application entry point from {entry.relative_path}",
                project_references=[entry.relative_path],
                evidence_references=entry.evidence_references,
                confidence=entry.confidence,
            ))
            parent = self._project_for_path(project_ids, entry.relative_path) or root_id
            relationships.append(ArchitectureRelationship(
                source_component_id=parent,
                target_component_id=cid,
                relationship_type="hosts",
                description="Static evidence identifies this as an application entry point.",
                status=RelationshipStatus.confirmed,
                evidence_references=entry.evidence_references,
                confidence=entry.confidence,
            ))

        exposed = [endpoint for endpoint in analysis.api_endpoints if endpoint.exposure.lower() == "exposed"]
        if exposed:
            api_refs = sorted({ref for endpoint in exposed for ref in endpoint.evidence_references})
            api_id = self._stable_id("api_boundary", "API Boundary")
            components.append(ArchitectureComponent(
                component_id=api_id,
                name="API Boundary",
                component_type="api_boundary",
                description="Routes explicitly exposed by repository code or framework configuration.",
                project_references=sorted({endpoint.relative_path for endpoint in exposed}),
                evidence_references=api_refs,
                confidence=self._confidence(analysis, api_refs, ConfidenceLevel.medium),
            ))
            relationships.append(ArchitectureRelationship(
                source_component_id=root_id,
                target_component_id=api_id,
                relationship_type="exposes",
                description="Repository static evidence exposes API routes.",
                status=RelationshipStatus.confirmed,
                evidence_references=api_refs,
                confidence=self._confidence(analysis, api_refs, ConfidenceLevel.medium),
            ))

        for index, database in enumerate(analysis.database_findings):
            cid = self._stable_id("database", database.technology, index)
            components.append(ArchitectureComponent(
                component_id=cid,
                name=database.technology,
                component_type="persistence",
                description=database.detail,
                project_references=[database.relative_path],
                evidence_references=database.evidence_references,
                confidence=database.confidence,
            ))
            relationships.append(ArchitectureRelationship(
                source_component_id=root_id,
                target_component_id=cid,
                relationship_type="uses_persistence",
                description="Static repository evidence configures or references persistence.",
                status=RelationshipStatus.confirmed,
                evidence_references=database.evidence_references,
                confidence=database.confidence,
            ))
            data_flows.append(ArchitectureDataFlow(
                source_component_id=root_id,
                target_component_id=cid,
                flow_description="Static evidence indicates a persistence interaction; runtime data movement is not established.",
                interaction_type="persistence access",
                evidence_references=database.evidence_references,
                confidence=database.confidence,
                status=RelationshipStatus.inferred,
            ))

        for index, integration in enumerate(analysis.external_integrations):
            status = RelationshipStatus.confirmed if integration.status.lower() == "confirmed" else RelationshipStatus.inferred
            eid = self._stable_id("external", integration.name, index)
            external_systems.append(ExternalSystem(
                external_system_id=eid,
                name=integration.name,
                integration_type=integration.integration_type,
                description=integration.detail,
                evidence_references=integration.evidence_references,
                confidence=integration.confidence,
                status=status,
            ))
            relationships.append(ArchitectureRelationship(
                source_component_id=root_id,
                target_component_id=eid,
                relationship_type="integrates_with",
                description=f"{'Confirmed' if status == RelationshipStatus.confirmed else 'Inferred'} integration: {integration.detail}",
                status=status,
                evidence_references=integration.evidence_references,
                confidence=integration.confidence,
            ))
            data_flows.append(ArchitectureDataFlow(
                source_component_id=root_id,
                target_component_id=eid,
                flow_description=f"{integration.integration_type} integration interaction evidenced in static repository files.",
                interaction_type=integration.integration_type,
                evidence_references=integration.evidence_references,
                confidence=integration.confidence,
                status=status,
            ))

        for dependency in analysis.dependencies:
            source_id = self._project_for_path(project_ids, dependency.source) or root_id
            target_id = self._project_for_path(project_ids, dependency.target)
            if target_id is None:
                continue
            status = RelationshipStatus.confirmed if dependency.resolved else RelationshipStatus.inferred
            relationships.append(ArchitectureRelationship(
                source_component_id=source_id,
                target_component_id=target_id,
                relationship_type=dependency.dependency_type,
                description=(
                    f"{'Resolved' if dependency.resolved else 'Unresolved'} static dependency from "
                    f"{dependency.source} to {dependency.target}."
                ),
                status=status,
                evidence_references=dependency.evidence_references,
                confidence=dependency.confidence,
            ))

        component_limit = list(components[:self.maximum_nodes])
        if len(components) > self.maximum_nodes:
            warnings.append(f"Architecture synthesis components limited to {self.maximum_nodes} items.")
            allowed_ids = {item.component_id for item in component_limit}
            remaining_external_slots = max(0, self.maximum_nodes - len(component_limit))
            external_systems = external_systems[:remaining_external_slots]
            allowed_ids.update(item.external_system_id for item in external_systems)
        else:
            allowed_ids = {item.component_id for item in component_limit}
            remaining_external_slots = max(0, self.maximum_nodes - len(component_limit))
            external_systems = external_systems[:remaining_external_slots]
            allowed_ids.update(item.external_system_id for item in external_systems)

        limited_relationships = [
            relationship for relationship in relationships
            if relationship.source_component_id in allowed_ids and relationship.target_component_id in allowed_ids
        ][:self.maximum_edges]
        if len(limited_relationships) < len(relationships):
            warnings.append(f"Architecture synthesis relationships limited to {self.maximum_edges} items.")

        components_by_id = {item.component_id: item for item in component_limit}
        limited_data_flows = [
            flow for flow in data_flows
            if flow.source_component_id in allowed_ids and flow.target_component_id in allowed_ids
        ][:self.maximum_edges]
        if len(limited_data_flows) < len(data_flows):
            warnings.append(f"Architecture synthesis data flows limited to {self.maximum_edges} items.")

        if not components_by_id:
            warnings.append("No supported architectural components could be synthesized from the analysis findings.")

        summary = self._summary(analysis, component_limit, limited_relationships, limited_data_flows)
        synthesis_metadata = ArchitectureSynthesisMetadata(
            synthesis_generated_at=datetime.now(timezone.utc).isoformat(),
            maximum_components=self.maximum_nodes,
            maximum_relationships=self.maximum_edges,
            options={"visualization_used": visualization is not None},
        )
        result = ArchitectureSynthesisResult(
            synthesis_id=uuid4(),
            original_analysis_id=analysis.analysis_id,
            repository_name=analysis.repository_name,
            components=component_limit,
            relationships=limited_relationships,
            data_flows=limited_data_flows,
            external_systems=[
                item for item in external_systems
                if item.external_system_id in allowed_ids
            ],
            architecture_summary=summary,
            warnings=list(dict.fromkeys(warnings)),
            limitations=list(dict.fromkeys(analysis.limitations)),
            synthesis_metadata=synthesis_metadata,
        )
        result.unified_diagram = self._unified_diagram(analysis, result)
        return result

    def _evidence_refs_for_paths(self, analysis: RepositoryAnalysisResult, paths: list[str]) -> list[str]:
        refs: list[str] = []
        path_set = set(paths)
        for evidence in analysis.evidence:
            if evidence.relative_path in path_set:
                refs.append(evidence.evidence_id)
        return sorted(set(refs))

    def _project_for_path(self, project_ids: dict[str, str], path: str) -> str | None:
        normalized = path.replace("\\", "/")
        for project_path, component_id in project_ids.items():
            project_normalized = project_path.replace("\\", "/")
            if normalized == project_normalized or normalized.startswith(project_normalized.rstrip("/") + "/"):
                return component_id
        return None

    def _summary(
        self,
        analysis: RepositoryAnalysisResult,
        components: list[ArchitectureComponent],
        relationships: list[ArchitectureRelationship],
        data_flows: list[ArchitectureDataFlow],
    ) -> str:
        inferred = sum(item.status == RelationshipStatus.inferred for item in relationships)
        return (
            f"Static repository synthesis for {analysis.repository_name} identified {len(components)} architectural "
            f"components, {len(relationships)} supported relationships, and {len(data_flows)} evidence-supported "
            f"interactions. {inferred} relationship(s) are inferred rather than directly established. "
            "No runtime communication or deployment topology is claimed."
        )

    def _unified_diagram(
        self,
        analysis: RepositoryAnalysisResult,
        synthesis: ArchitectureSynthesisResult,
    ) -> ArchitectureDiagram:
        lines = ["flowchart LR"]
        nodes: list[DiagramNode] = []
        relationships: list[DiagramRelationship] = []
        node_refs: dict[str, list[str]] = {}
        relationship_refs: dict[str, list[str]] = {}

        for component in synthesis.components:
            evidence = self.evidence_mapper.map_evidence(
                analysis, component.evidence_references, component.component_id
            )
            nodes.append(DiagramNode(
                node_id=component.component_id,
                label=self._label(component.name),
                origin="Architecture synthesis component",
                evidence_references=evidence,
            ))
            node_refs[component.component_id] = component.evidence_references
            lines.append(
                f'    {component.component_id}["{self._label(component.name)}"]'
            )

        for external in synthesis.external_systems:
            evidence = self.evidence_mapper.map_evidence(
                analysis, external.evidence_references, external.external_system_id
            )
            nodes.append(DiagramNode(
                node_id=external.external_system_id,
                label=self._label(external.name),
                origin="Architecture synthesis external system",
                evidence_references=evidence,
            ))
            node_refs[external.external_system_id] = external.evidence_references
            lines.append(
                f'    {external.external_system_id}{{{{"{self._label(external.name)}"}}}}'
            )

        for relationship in synthesis.relationships[:self.maximum_edges]:
            status_suffix = " (inferred)" if relationship.status == RelationshipStatus.inferred else ""
            evidence = self.evidence_mapper.map_evidence(
                analysis, relationship.evidence_references, "architecture_relationship"
            )
            relationship_id = f"{relationship.source_component_id}->{relationship.target_component_id}"
            label = self._label(relationship.relationship_type.replace("_", " ") + status_suffix)
            relationships.append(DiagramRelationship(
                source_node_id=relationship.source_component_id,
                target_node_id=relationship.target_component_id,
                relationship_type=relationship.relationship_type,
                label=label,
                evidence_references=evidence,
            ))
            relationship_refs[relationship_id] = relationship.evidence_references
            lines.append(
                f'    {relationship.source_component_id} -->|{label}| {relationship.target_component_id}'
            )

        existing_pairs = {
            (relationship.source_node_id, relationship.target_node_id)
            for relationship in relationships
        }
        edge_slots = self.maximum_edges - len(relationships)
        flow_count = 0
        for data_flow in synthesis.data_flows:
            pair = (data_flow.source_component_id, data_flow.target_component_id)
            if flow_count >= edge_slots or pair in existing_pairs:
                continue
            evidence = self.evidence_mapper.map_evidence(
                analysis, data_flow.evidence_references, "architecture_data_flow"
            )
            label = self._label(
                f"data flow: {data_flow.interaction_type or 'interaction'}"
                + (" (inferred)" if data_flow.status == RelationshipStatus.inferred else "")
            )
            relationships.append(DiagramRelationship(
                source_node_id=data_flow.source_component_id,
                target_node_id=data_flow.target_component_id,
                relationship_type="data_flow",
                label=label,
                evidence_references=evidence,
            ))
            relationship_refs[pair[0] + "->" + pair[1]] = data_flow.evidence_references
            lines.append(
                f'    {data_flow.source_component_id} -->|{label}| {data_flow.target_component_id}'
            )
            existing_pairs.add(pair)
            flow_count += 1

        evidence_ids = sorted({
            evidence.evidence_id for node in nodes for evidence in node.evidence_references
        })
        diagram = ArchitectureDiagram(
            diagram_id="unified_architecture",
            title="Unified Architecture",
            diagram_type=DiagramType.component,
            description="Unified high-level architecture synthesized from repository analysis evidence.",
            mermaid_source="\n".join(lines),
            nodes=nodes,
            relationships=relationships,
            evidence_references=evidence_ids,
            evidence_map=self.evidence_mapper.evidence_map(
                analysis, node_refs, relationship_refs
            ),
            generation_warnings=[],
        )
        validation = self.validator.validate(diagram, analysis)
        if not validation.valid:
            diagram.generation_warnings.extend(validation.errors)
            synthesis.warnings.extend(validation.errors)
        elif not nodes:
            diagram.generation_warnings.append("No nodes could be derived from repository evidence.")
        return diagram


def external_systems_as_components(
    external_systems: list[ExternalSystem],
    allowed_ids: set[str],
    analysis: RepositoryAnalysisResult,
) -> list[ArchitectureComponent]:
    return [
        ArchitectureComponent(
            component_id=item.external_system_id,
            name=item.name,
            component_type="external_system",
            description=item.description,
            evidence_references=item.evidence_references,
            confidence=item.confidence,
        )
        for item in external_systems
        if item.external_system_id in allowed_ids
    ]
