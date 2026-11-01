from pydantic import ValidationError

from app.evaluation.models import Criterion, EvaluationCase, MetricResult


def result(metric: str, passed: bool, explanation: str, category: str) -> MetricResult:
    return MetricResult(metric=metric, status="passed" if passed else "failed",
                        score=1 if passed else 0, explanation=explanation,
                        category=None if passed else category)


def evaluate_metric(case: EvaluationCase, criterion: Criterion) -> MetricResult:
    metric = criterion.metric
    if metric == "normalized_match":
        if case.reference is None:
            return MetricResult(metric=metric, status="not_applicable",
                                explanation="No reference answer is available.")
        def normalize(value):
            return " ".join(value.casefold().split()) if isinstance(value, str) else value
        return result(metric, normalize(case.output) == normalize(case.reference),
                      "Normalized reference comparison.", "reference_mismatch")
    if metric == "required_fields":
        if not criterion.fields:
            return MetricResult(metric=metric, status="not_applicable",
                                explanation="No required fields configured.")
        passed = isinstance(case.output, dict) and all(
            name in case.output and case.output[name] not in (None, "", [])
            for name in criterion.fields
        )
        return result(metric, passed, "Required nonempty fields checked.", "missing_fields")
    if metric == "contains":
        if not isinstance(case.output, str) or not criterion.fields:
            return MetricResult(metric=metric, status="not_applicable",
                                explanation="Text and required phrases are needed.")
        return result(metric, all(item.casefold() in case.output.casefold() for item in criterion.fields),
                      "Required phrases checked; not a semantic correctness score.", "missing_content")
    if metric == "sources":
        if case.valid_sources is None:
            return MetricResult(metric=metric, status="not_applicable",
                                explanation="No source judgments available.")
        sources = case.output.get("sources") if isinstance(case.output, dict) else None
        valid = isinstance(sources, list) and all(
            isinstance(item, str) and item in case.valid_sources for item in sources
        )
        return result(metric, valid, "Source identifiers checked.", "invalid_source")
    from app.api.schemas import ArchitectureResponse, ArchitectureReview, GeneratedRAGAnswer, RequirementAnalysis
    from app.repository.reporting.models import ArchitectureReport
    from app.repository.reporting.validation import validate_report, ReportValidationError
    schemas = {
        "requirements": RequirementAnalysis, "architecture": ArchitectureResponse,
        "review": ArchitectureReview, "report": ArchitectureReport, "rag": GeneratedRAGAnswer,
    }
    if criterion.schema_name is None:
        return MetricResult(metric=metric, status="not_applicable", explanation="No schema selected.")
    try:
        parsed = schemas[criterion.schema_name].model_validate(case.output)
        if isinstance(parsed, ArchitectureReport):
            validate_report(parsed)
    except (ValidationError, ReportValidationError):
        return result(metric, False, "Output violates the application schema.", "invalid_schema")
    return result(metric, True, "Application schema validated.", "invalid_schema")
