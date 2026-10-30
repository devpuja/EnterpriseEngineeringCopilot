from collections import defaultdict

from app.repository.analysis.models import ConfidenceLevel
from app.repository.synthesis.models import ArchitectureSynthesisResult, RelationshipStatus
from app.repository.review.models import (
    ArchitectureReviewCategory,
    ArchitectureReviewFinding,
    ArchitectureReviewFindingStatus,
    ArchitectureReviewSeverity,
)


STRUCTURAL_TYPES = {
    "contains",
    "hosts",
    "exposes",
    "uses_persistence",
    "integrates_with",
}


def is_dependency_relationship(relationship_type: str) -> bool:
    normalized = relationship_type.strip().lower()
    return normalized not in STRUCTURAL_TYPES


class DeterministicArchitectureReviewChecks:
    def finding(
        self,
        *,
        synthesis_id: str,
        rule_id: str,
        title: str,
        description: str,
        category: ArchitectureReviewCategory,
        severity: ArchitectureReviewSeverity,
        status: ArchitectureReviewFindingStatus,
        component_ids: list[str] | None = None,
        relationships: list[str] | None = None,
        data_flows: list[str] | None = None,
        evidence: list[str] | None = None,
        confidence: ConfidenceLevel = ConfidenceLevel.medium,
        recommendation: str,
        benefits: list[str] | None = None,
        trade_offs: list[str] | None = None,
        considerations: list[str] | None = None,
    ) -> ArchitectureReviewFinding:
        import hashlib

        key = "|".join([
            synthesis_id,
            rule_id,
            title,
            ",".join(sorted(set(component_ids or []))),
            ",".join(sorted(set(evidence or []))),
        ])
        finding_id = "AR_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12].upper()
        return ArchitectureReviewFinding(
            finding_id=finding_id,
            rule_id=rule_id,
            title=title,
            description=description,
            category=category,
            severity=severity,
            status=status,
            affected_component_ids=sorted(set(component_ids or [])),
            related_relationships=sorted(set(relationships or [])),
            related_data_flows=sorted(set(data_flows or [])),
            related_relationship_references=sorted(set(relationships or [])),
            related_data_flow_references=sorted(set(data_flows or [])),
            evidence_references=sorted(set(evidence or [])),
            confidence=confidence,
            recommendation=recommendation,
            benefits=list(dict.fromkeys(benefits or [])),
            trade_offs=list(dict.fromkeys(trade_offs or [])),
            implementation_considerations=list(dict.fromkeys(considerations or [])),
        )

    def run(self, synthesis: ArchitectureSynthesisResult, valid_evidence_ids: set[str]) -> list[ArchitectureReviewFinding]:
        findings: list[ArchitectureReviewFinding] = []
        sid = str(synthesis.synthesis_id)
        component_ids = {item.component_id for item in synthesis.components}

        if not synthesis.components:
            findings.append(self.finding(
                synthesis_id=sid,
                rule_id="ARCH-001",
                title="No architectural components were synthesized",
                description="The synthesis contains no components, so a structural review cannot establish architecture boundaries.",
                category=ArchitectureReviewCategory.architecture_structure,
                severity=ArchitectureReviewSeverity.high,
                status=ArchitectureReviewFindingStatus.needs_investigation,
                evidence=[],
                confidence=ConfidenceLevel.low,
                recommendation="Investigate the repository analysis completeness before relying on the synthesis as an architecture model.",
                benefits=["Clarifies whether analysis or synthesis data is incomplete."],
                trade_offs=["Further repository analysis may be required."],
            ))

        for component in synthesis.components:
            evidence = [ref for ref in component.evidence_references if ref in valid_evidence_ids]
            vague = len(component.description.strip()) < 20 or "identified from" in component.description.lower()
            if not evidence and (vague or component.component_type == "repository"):
                findings.append(self.finding(
                    synthesis_id=sid,
                    rule_id="ARCH-002",
                    title=f"Insufficient evidence for {component.name}",
                    description="The component is present in the synthesis but has no preserved, valid evidence reference for its responsibility.",
                    category=ArchitectureReviewCategory.architecture_structure,
                    severity=ArchitectureReviewSeverity.medium,
                    status=ArchitectureReviewFindingStatus.needs_investigation,
                    component_ids=[component.component_id],
                    evidence=[],
                    confidence=ConfidenceLevel.low,
                    recommendation=f"Verify the responsibility and boundary of {component.name} against source files and add evidence-backed context.",
                    benefits=["Improves architecture traceability and component accountability."],
                    trade_offs=["Requires manual source review and may discover synthesis omissions."],
                ))
            elif vague:
                findings.append(self.finding(
                    synthesis_id=sid,
                    rule_id="ARCH-003",
                    title=f"Responsibility for {component.name} may be unclear",
                    description="The synthesized component description is generic or insufficient to explain its responsibility.",
                    category=ArchitectureReviewCategory.architecture_structure,
                    severity=ArchitectureReviewSeverity.low,
                    status=ArchitectureReviewFindingStatus.inferred,
                    component_ids=[component.component_id],
                    evidence=evidence,
                    confidence=component.confidence if component.confidence != ConfidenceLevel.high else ConfidenceLevel.medium,
                    recommendation=f"Clarify the responsibility and ownership boundary of {component.name} in the architecture documentation.",
                    benefits=["Makes change impact and ownership easier to reason about."],
                    trade_offs=["Documentation detail may need validation against source behavior."],
                ))

        unresolved = [
            rel for rel in synthesis.relationships
            if is_dependency_relationship(rel.relationship_type)
            and (
                rel.status == RelationshipStatus.inferred
                or "unresolved" in rel.description.lower()
            )
        ]
        for rel in unresolved:
            evidence = [ref for ref in rel.evidence_references if ref in valid_evidence_ids]
            status = (
                ArchitectureReviewFindingStatus.needs_investigation
                if not evidence
                else ArchitectureReviewFindingStatus.inferred
            )
            findings.append(self.finding(
                synthesis_id=sid,
                rule_id="DEP-001",
                title="Unresolved or inferred dependency relationship",
                description=f"The relationship from {rel.source_component_id} to {rel.target_component_id} is unresolved or inferred from static evidence.",
                category=ArchitectureReviewCategory.dependencies_coupling,
                severity=ArchitectureReviewSeverity.medium if status == ArchitectureReviewFindingStatus.inferred else ArchitectureReviewSeverity.high,
                status=status,
                component_ids=[rel.source_component_id, rel.target_component_id],
                relationships=[f"{rel.source_component_id}->{rel.target_component_id}:{rel.relationship_type}"],
                evidence=evidence,
                confidence=rel.confidence,
                recommendation="Verify whether the dependency target resolves and document the intended module boundary.",
                benefits=["Reduces uncertainty in dependency direction and change impact."],
                trade_offs=["Confirmation requires source build or configuration context beyond this static review."],
            ))

        outgoing: dict[str, list[str]] = defaultdict(list)
        for rel in synthesis.relationships:
            if rel.relationship_type not in STRUCTURAL_TYPES and rel.source_component_id in component_ids:
                outgoing[rel.source_component_id].append(rel.target_component_id)
        for component_id, targets in outgoing.items():
            if len(set(targets)) >= 5:
                evidence = sorted({
                    ref
                    for rel in synthesis.relationships
                    if rel.source_component_id == component_id
                    for ref in rel.evidence_references
                    if ref in valid_evidence_ids
                })
                findings.append(self.finding(
                    synthesis_id=sid,
                    rule_id="DEP-002",
                    title="High dependency concentration",
                    description=f"Component {component_id} has relationships to {len(set(targets))} distinct synthesized targets.",
                    category=ArchitectureReviewCategory.dependencies_coupling,
                    severity=ArchitectureReviewSeverity.medium,
                    status=ArchitectureReviewFindingStatus.confirmed if evidence else ArchitectureReviewFindingStatus.inferred,
                    component_ids=[component_id, *sorted(set(targets))],
                    relationships=[f"{component_id}->{target}" for target in sorted(set(targets))],
                    evidence=evidence,
                    confidence=ConfidenceLevel.medium,
                    recommendation="Review the component's dependency boundaries and split or isolate responsibilities only where the source evidence supports it.",
                    benefits=["Can reduce change coupling and improve testability."],
                    trade_offs=["Splitting dependencies may add interfaces and coordination overhead."],
                ))

        confirmed_dependency_graph: dict[str, set[str]] = defaultdict(set)
        for rel in synthesis.relationships:
            if rel.relationship_type not in STRUCTURAL_TYPES and rel.status == RelationshipStatus.confirmed:
                confirmed_dependency_graph[rel.source_component_id].add(rel.target_component_id)

        def has_cycle() -> list[list[str]]:
            cycles: list[list[str]] = []
            visited: set[str] = set()
            path: list[str] = []

            def visit(node: str) -> None:
                if node in path:
                    start = path.index(node)
                    cycle = path[start:] + [node]
                    key = tuple(sorted(set(cycle)))
                    if not any(tuple(sorted(set(existing))) == key for existing in cycles):
                        cycles.append(cycle)
                    return
                if node in visited:
                    return
                visited.add(node)
                path.append(node)
                for target in sorted(confirmed_dependency_graph.get(node, set())):
                    visit(target)
                path.pop()

            for source in sorted(confirmed_dependency_graph):
                visit(source)
            return cycles

        for cycle in has_cycle():
            component_ids_in_cycle = sorted({item for item in cycle if item in component_ids})
            if len(component_ids_in_cycle) < 2:
                continue
            evidence = sorted({
                ref
                for rel in synthesis.relationships
                if rel.source_component_id in component_ids_in_cycle
                and rel.target_component_id in component_ids_in_cycle
                for ref in rel.evidence_references
                if ref in valid_evidence_ids
            })
            findings.append(self.finding(
                synthesis_id=sid,
                rule_id="DEP-003",
                title="Potential circular dependency",
                description="Confirmed synthesized dependency relationships form a circular component path.",
                category=ArchitectureReviewCategory.dependencies_coupling,
                severity=ArchitectureReviewSeverity.high,
                status=ArchitectureReviewFindingStatus.confirmed if evidence else ArchitectureReviewFindingStatus.needs_investigation,
                component_ids=component_ids_in_cycle,
                relationships=[f"{source}->{target}" for source in component_ids_in_cycle for target in component_ids_in_cycle if target in confirmed_dependency_graph.get(source, set())],
                evidence=evidence,
                confidence=ConfidenceLevel.high if evidence else ConfidenceLevel.low,
                recommendation="Inspect the cycle in source dependency configuration and break it through a shared abstraction or boundary if confirmed.",
                benefits=["Reduces build, testing, and change coupling."],
                trade_offs=["Refactoring may introduce interfaces or change package ownership."],
            ))

        for external in synthesis.external_systems:
            evidence = [ref for ref in external.evidence_references if ref in valid_evidence_ids]
            if not evidence or external.status == RelationshipStatus.inferred:
                findings.append(self.finding(
                    synthesis_id=sid,
                    rule_id="INT-001",
                    title=f"Incomplete integration evidence for {external.name}",
                    description="The external integration has inferred or incomplete evidence; protocol, ownership, and runtime behavior remain unconfirmed.",
                    category=ArchitectureReviewCategory.integration_architecture,
                    severity=ArchitectureReviewSeverity.medium,
                    status=ArchitectureReviewFindingStatus.inferred if evidence else ArchitectureReviewFindingStatus.needs_investigation,
                    component_ids=[external.external_system_id],
                    evidence=evidence,
                    confidence=external.confidence,
                    recommendation=f"Document the integration contract and boundary for {external.name}; verify ownership and failure behavior outside static analysis.",
                    benefits=["Clarifies integration ownership and responsibilities."],
                    trade_offs=["Contract documentation or integration tests may be required."],
                ))

        valid_flow_pairs = {(rel.source_component_id, rel.target_component_id) for rel in synthesis.relationships}
        for flow in synthesis.data_flows:
            evidence = [ref for ref in flow.evidence_references if ref in valid_evidence_ids]
            if flow.source_component_id not in component_ids and flow.source_component_id not in {external.external_system_id for external in synthesis.external_systems}:
                findings.append(self.finding(
                    synthesis_id=sid,
                    rule_id="DATA-001",
                    title="Data flow references an unknown source",
                    description=f"Data flow source {flow.source_component_id} is absent from the synthesized component and external-system IDs.",
                    category=ArchitectureReviewCategory.data_flow,
                    severity=ArchitectureReviewSeverity.medium,
                    status=ArchitectureReviewFindingStatus.confirmed if evidence else ArchitectureReviewFindingStatus.needs_investigation,
                    evidence=evidence,
                    confidence=ConfidenceLevel.low,
                    recommendation="Correct the synthesis data-flow endpoint or verify the missing component in repository analysis.",
                    benefits=["Restores consistency between architecture relationships and data flows."],
                    trade_offs=["May require rebuilding the synthesis from corrected evidence."],
                ))
            if flow.target_component_id not in component_ids and flow.target_component_id not in {external.external_system_id for external in synthesis.external_systems}:
                findings.append(self.finding(
                    synthesis_id=sid,
                    rule_id="DATA-002",
                    title="Data flow references an unknown target",
                    description=f"Data flow target {flow.target_component_id} is absent from the synthesized component and external-system IDs.",
                    category=ArchitectureReviewCategory.data_flow,
                    severity=ArchitectureReviewSeverity.medium,
                    status=ArchitectureReviewFindingStatus.confirmed if evidence else ArchitectureReviewFindingStatus.needs_investigation,
                    evidence=evidence,
                    confidence=ConfidenceLevel.low,
                    recommendation="Correct the synthesis data-flow endpoint or verify the missing target in repository analysis.",
                    benefits=["Restores consistency between architecture relationships and data flows."],
                    trade_offs=["May require rebuilding the synthesis from corrected evidence."],
                ))
            if (flow.source_component_id, flow.target_component_id) not in valid_flow_pairs and flow.evidence_references:
                findings.append(self.finding(
                    synthesis_id=sid,
                    rule_id="DATA-003",
                    title="Data flow has no corresponding relationship",
                    description="A data-flow path is represented without a matching synthesized architecture relationship.",
                    category=ArchitectureReviewCategory.data_flow,
                    severity=ArchitectureReviewSeverity.low,
                    status=ArchitectureReviewFindingStatus.inferred,
                    component_ids=[flow.source_component_id, flow.target_component_id],
                    data_flows=[f"{flow.source_component_id}->{flow.target_component_id}:{flow.interaction_type or 'interaction'}"],
                    evidence=evidence,
                    confidence=flow.confidence,
                    recommendation="Align the data-flow path with its supporting relationship model or remove unsupported synthesis detail.",
                    benefits=["Improves consistency and traceability across architecture views."],
                    trade_offs=["Editing may require more detailed evidence and synthesis reruns."],
                ))

        if synthesis.warnings or synthesis.limitations:
            findings.append(self.finding(
                synthesis_id=sid,
                rule_id="EVID-001",
                title="Synthesis evidence has limitations",
                description="The synthesis reports warnings or limitations, so review conclusions should be treated as partial static evidence.",
                category=ArchitectureReviewCategory.evidence_quality,
                severity=ArchitectureReviewSeverity.low,
                status=ArchitectureReviewFindingStatus.needs_investigation,
                evidence=[],
                confidence=ConfidenceLevel.medium,
                recommendation="Review the synthesis limitations alongside repository evidence before making architectural decisions.",
                benefits=["Keeps evidence gaps visible and prevents unsupported conclusions."],
                trade_offs=["Some questions cannot be resolved without additional repository or runtime context."],
            ))

        return list({item.finding_id: item for item in findings}.values())
