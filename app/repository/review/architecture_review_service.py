from datetime import datetime, timezone
from uuid import uuid4

from app.repository.analysis.models import ConfidenceLevel, RepositoryAnalysisResult
from app.repository.synthesis.models import ArchitectureSynthesisResult
from app.repository.review.deterministic_checks import DeterministicArchitectureReviewChecks
from app.repository.review.models import (
    ArchitectureReviewFinding,
    ArchitectureReviewFindingStatus,
    ArchitectureReviewOutcome,
    ArchitectureReviewRecommendation,
    ArchitectureReviewResult,
    ArchitectureReviewSeverity,
    ArchitectureReviewStrength,
)


class ArchitectureReviewService:
    def __init__(self, checks: DeterministicArchitectureReviewChecks | None = None):
        self.checks = checks or DeterministicArchitectureReviewChecks()

    def _valid_evidence_ids(
        self,
        synthesis: ArchitectureSynthesisResult,
        analysis: RepositoryAnalysisResult | None,
    ) -> set[str]:
        ids: set[str] = set()
        if analysis is not None:
            ids.update(item.evidence_id for item in analysis.evidence)
            for field_items in (
                analysis.projects,
                analysis.application_entry_points,
                analysis.dependencies,
                analysis.api_endpoints,
                analysis.database_findings,
                analysis.external_integrations,
                analysis.architectural_patterns,
            ):
                for item in field_items:
                    ids.update(getattr(item, "evidence_references", getattr(item, "evidence", [])))
        for component in synthesis.components:
            ids.update(component.evidence_references)
        for relationship in synthesis.relationships:
            ids.update(relationship.evidence_references)
        for flow in synthesis.data_flows:
            ids.update(flow.evidence_references)
        for external in synthesis.external_systems:
            ids.update(external.evidence_references)
        return ids

    def _outcome(self, findings: list[ArchitectureReviewFinding]) -> ArchitectureReviewOutcome:
        critical_confirmed = [
            item for item in findings
            if item.status == ArchitectureReviewFindingStatus.confirmed
            and item.severity == ArchitectureReviewSeverity.critical
        ]
        high_confirmed = [
            item for item in findings
            if item.status == ArchitectureReviewFindingStatus.confirmed
            and item.severity == ArchitectureReviewSeverity.high
        ]
        if critical_confirmed or len(high_confirmed) >= 2:
            return ArchitectureReviewOutcome.significant_risks

        investigation = [
            item for item in findings
            if item.status == ArchitectureReviewFindingStatus.needs_investigation
        ]
        if investigation and not high_confirmed and not critical_confirmed:
            return ArchitectureReviewOutcome.needs_investigation

        actionable = [
            item for item in findings
            if item.status in {
                ArchitectureReviewFindingStatus.confirmed,
                ArchitectureReviewFindingStatus.inferred,
            }
            and item.severity in {
                ArchitectureReviewSeverity.critical,
                ArchitectureReviewSeverity.high,
                ArchitectureReviewSeverity.medium,
                ArchitectureReviewSeverity.low,
            }
        ]
        if actionable or high_confirmed:
            return ArchitectureReviewOutcome.improvements_recommended
        return ArchitectureReviewOutcome.healthy

    def _strengths(
        self,
        synthesis: ArchitectureSynthesisResult,
        valid_evidence_ids: set[str],
    ) -> list[ArchitectureReviewStrength]:
        strengths: list[ArchitectureReviewStrength] = []
        evidenced = [
            component for component in synthesis.components
            if component.evidence_references
            and any(ref in valid_evidence_ids for ref in component.evidence_references)
        ]
        if evidenced:
            refs = sorted({
                ref for component in evidenced for ref in component.evidence_references
                if ref in valid_evidence_ids
            })
            strengths.append(ArchitectureReviewStrength(
                title="Architecture components are traceable to repository evidence",
                description=f"{len(evidenced)} synthesized component(s) include preserved evidence references.",
                evidence_references=refs[:30],
                affected_component_ids=[component.component_id for component in evidenced],
                confidence=ConfidenceLevel.high,
            ))
        confirmed_relationships = [
            relationship for relationship in synthesis.relationships
            if relationship.status.value == "confirmed"
            and relationship.evidence_references
            and any(ref in valid_evidence_ids for ref in relationship.evidence_references)
        ]
        if confirmed_relationships:
            refs = sorted({
                ref for relationship in confirmed_relationships for ref in relationship.evidence_references
                if ref in valid_evidence_ids
            })
            strengths.append(ArchitectureReviewStrength(
                title="Confirmed relationships are evidence-backed",
                description=f"{len(confirmed_relationships)} confirmed relationship(s) have supporting evidence references.",
                evidence_references=refs[:30],
                confidence=ConfidenceLevel.high,
            ))
        if synthesis.data_flows and any(flow.evidence_references for flow in synthesis.data_flows):
            strengths.append(ArchitectureReviewStrength(
                title="Synthesis preserves traceable data flows",
                description=f"{len(synthesis.data_flows)} data-flow path(s) are represented with source, target, and evidence metadata.",
                evidence_references=sorted({
                    ref for flow in synthesis.data_flows for ref in flow.evidence_references
                    if ref in valid_evidence_ids
                })[:30],
                confidence=ConfidenceLevel.medium,
            ))
        return strengths

    def review(
        self,
        synthesis: ArchitectureSynthesisResult,
        analysis: RepositoryAnalysisResult | None = None,
    ) -> ArchitectureReviewResult:
        if analysis is not None and analysis.analysis_id != synthesis.original_analysis_id:
            warnings = [
                "The optional RepositoryAnalysisResult does not match the synthesis original_analysis_id and was not used for review evidence."
            ]
            analysis = None
        else:
            warnings = []

        valid_evidence_ids = self._valid_evidence_ids(synthesis, analysis)
        findings = self.checks.run(synthesis, valid_evidence_ids)
        findings = sorted(
            findings,
            key=lambda item: (
                {"critical": 0, "high": 1, "medium": 2, "low": 3, "informational": 4}[item.severity.value],
                item.title,
            ),
        )
        outcome = self._outcome(findings)
        strengths = self._strengths(synthesis, valid_evidence_ids)

        priority: list[ArchitectureReviewRecommendation] = []
        for finding in findings[:5]:
            priority.append(ArchitectureReviewRecommendation(
                recommendation=finding.recommendation,
                benefits=finding.benefits,
                trade_offs=finding.trade_offs,
                implementation_considerations=finding.implementation_considerations,
                priority=("high" if finding.severity.value in {"critical", "high"} else "medium"),
                implementation_effort="medium",
            ))

        warnings.extend(synthesis.warnings)
        limitations = list(dict.fromkeys(synthesis.limitations))
        if analysis is not None:
            warnings.extend(analysis.analysis_warnings)
            limitations.extend(analysis.limitations)
        warnings = list(dict.fromkeys(warnings))
        limitations = list(dict.fromkeys(limitations))

        confirmed = sum(item.status == ArchitectureReviewFindingStatus.confirmed for item in findings)
        inferred = sum(item.status == ArchitectureReviewFindingStatus.inferred for item in findings)
        investigation = sum(item.status == ArchitectureReviewFindingStatus.needs_investigation for item in findings)
        summary = (
            f"Reviewed {len(synthesis.components)} component(s), {len(synthesis.relationships)} relationship(s), "
            f"{len(synthesis.external_systems)} external system(s), and {len(synthesis.data_flows)} data flow(s). "
            f"Outcome: {outcome.value}. Confirmed: {confirmed}; inferred: {inferred}; investigation: {investigation}."
        )
        return ArchitectureReviewResult(
            review_id=uuid4(),
            original_synthesis_id=synthesis.synthesis_id,
            original_analysis_id=synthesis.original_analysis_id,
            repository_name=synthesis.repository_name,
            review_summary=summary,
            overall_review_outcome=outcome,
            findings=findings,
            strengths=strengths,
            priority_recommendations=priority,
            warnings=warnings,
            limitations=limitations,
            review_metadata={
                "review_generated_at": datetime.now(timezone.utc).isoformat(),
                "review_version": "1",
                "deterministic": True,
                "analysis_used": analysis is not None,
                "confirmed_finding_count": confirmed,
                "inferred_finding_count": inferred,
                "investigation_finding_count": investigation,
            },
        )
