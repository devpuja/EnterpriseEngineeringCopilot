import asyncio
import logging

from app.repository.analysis.api_analyzer import APIAnalyzer
from app.repository.analysis.architecture_pattern_detector import ArchitecturePatternDetector
from app.repository.analysis.content_access import SnapshotContentReader
from app.repository.analysis.database_analyzer import DatabaseAnalyzer
from app.repository.analysis.dependency_analyzer import DependencyAnalyzer
from app.repository.analysis.evidence_collector import EvidenceCollector
from app.repository.analysis.integration_analyzer import IntegrationAnalyzer
from app.repository.analysis.models import RepositoryAnalysisResult
from app.repository.analysis.project_structure_analyzer import ProjectStructureAnalyzer
from app.repository.analysis.technology_detector import TechnologyDetector
from app.repository.models import RepositorySnapshot
from app.repository.workspace_manager import WorkspaceManager


logger = logging.getLogger(__name__)


class RepositoryAnalyzer:
    def __init__(self, workspace_manager: WorkspaceManager | None = None):
        self.workspace_manager = workspace_manager or WorkspaceManager()
        self.reader = SnapshotContentReader(self.workspace_manager)
        self.technology_detector = TechnologyDetector()
        self.project_structure_analyzer = ProjectStructureAnalyzer()
        self.dependency_analyzer = DependencyAnalyzer()
        self.api_analyzer = APIAnalyzer()
        self.database_analyzer = DatabaseAnalyzer()
        self.integration_analyzer = IntegrationAnalyzer()
        self.pattern_detector = ArchitecturePatternDetector()

    def analyze(self, snapshot: RepositorySnapshot) -> RepositoryAnalysisResult:
        evidence = EvidenceCollector()
        warnings: list[str] = []
        technology_stack = []
        technologies: set[str] = set()
        try:
            technology_stack, technologies = self.technology_detector.detect(snapshot, self.reader, evidence)
        except Exception as exc:
            warnings.append("Technology detection completed partially or was unavailable.")
            logger.warning("event=repository_analysis_stage_failed stage=technology error_type=%s", type(exc).__name__)

        projects = []
        entry_points = []
        structure = None
        try:
            projects, entry_points, structure = self.project_structure_analyzer.analyze(snapshot, self.reader, evidence)
        except Exception as exc:
            warnings.append("Project structure analysis completed partially or was unavailable.")
            logger.warning("event=repository_analysis_stage_failed stage=project_structure error_type=%s", type(exc).__name__)
            from app.repository.analysis.models import ProjectStructureFinding
            structure = ProjectStructureFinding(summary="Project structure could not be fully determined from static evidence.")

        stages = (
            ("dependencies", self.dependency_analyzer.analyze),
            ("api", self.api_analyzer.analyze),
            ("database", self.database_analyzer.analyze),
            ("integrations", self.integration_analyzer.analyze),
            ("patterns", self.pattern_detector.detect),
        )
        dependencies = []
        api_endpoints = []
        database_findings = []
        integrations = []
        patterns = []
        for stage_name, analyzer in stages:
            try:
                result = analyzer(snapshot, self.reader, evidence)
                if stage_name == "dependencies":
                    dependencies = result
                elif stage_name == "api":
                    api_endpoints = result
                elif stage_name == "database":
                    database_findings = result
                elif stage_name == "integrations":
                    integrations = result
                else:
                    patterns = result
            except Exception as exc:
                warnings.append(f"{stage_name.title()} analysis completed partially or was unavailable.")
                logger.warning("event=repository_analysis_stage_failed stage=%s error_type=%s", stage_name, type(exc).__name__)

        if not patterns:
            from app.repository.analysis.models import ArchitecturePatternFinding, ConfidenceLevel
            patterns = [ArchitecturePatternFinding(
                name="Not determined",
                evidence=["Architecture pattern analysis was unavailable or produced no sufficient evidence."],
                relevant_files=[],
                explanation="No sufficiently specific architecture pattern could be determined.",
                confidence=ConfidenceLevel.low,
                limitations="Static evidence was incomplete.",
            )]

        limitations = [
            "Static analysis only; runtime behavior and deployment topology were not observed.",
            "Dependency relationships and framework configuration are limited to evidence in discovered text files.",
        ]
        technology_summary = ", ".join(sorted({item.name for item in technology_stack})) or "No supported technology evidence determined"
        summary = (
            f"Analyzed {snapshot.repository_name} using static repository evidence. "
            f"Detected technologies: {technology_summary}. "
            f"Identified {len(projects)} project/package findings, {len(entry_points)} entry points, "
            f"{len(api_endpoints)} API route/client findings, and {len(patterns)} architectural pattern results."
        )
        logger.info(
            "event=repository_analysis_completed repository_name=%s technologies=%s findings=%s",
            snapshot.repository_name,
            len(technology_stack),
            len(evidence.items),
        )
        return RepositoryAnalysisResult(
            analysis_id=snapshot.analysis_id,
            repository_name=snapshot.repository_name,
            source_type=snapshot.source_type,
            source_reference=snapshot.source_reference,
            technology_stack=technology_stack,
            projects=projects,
            application_entry_points=entry_points,
            project_structure=structure,
            dependencies=dependencies,
            api_endpoints=api_endpoints,
            database_findings=database_findings,
            external_integrations=integrations,
            architectural_patterns=patterns,
            evidence=evidence.items,
            analysis_warnings=warnings,
            limitations=limitations,
            summary=summary,
        )

    async def aanalyze(self, snapshot: RepositorySnapshot) -> RepositoryAnalysisResult:
        return await asyncio.to_thread(self.analyze, snapshot)
