from typing import Protocol, runtime_checkable

from app.repository.analysis.models import RepositoryAnalysisResult
from app.repository.synthesis.models import ArchitectureSynthesisResult
from app.repository.review.models import ArchitectureReviewResult


@runtime_checkable
class ArchitectureReviewContract(Protocol):
    def review(
        self,
        synthesis: ArchitectureSynthesisResult,
        analysis: RepositoryAnalysisResult | None = None,
    ) -> ArchitectureReviewResult:
        ...
