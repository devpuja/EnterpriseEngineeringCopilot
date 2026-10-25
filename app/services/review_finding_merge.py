
import re
from difflib import SequenceMatcher

from app.api.schemas import ArchitectureReviewFinding


_SEVERITY_RANK = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


def _normalize(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))



def _issue_family(finding: ArchitectureReviewFinding) -> str | None:
    title = _normalize(finding.finding)

    title_families: dict[str, tuple[str, ...]] = {
        "diagram_component_mismatch": (
            "diagram node",
            "no matching architecture component",
            "undeclared component",
        ),
        "tenant_isolation": (
            "tenant isolation",
            "tenant scoped authorization",
            "tenant scoped access",
            "tenant data",
            "data leakage between tenants",
            "cross tenant",
            "multi tenancy",
            "multi tenant",
        ),
        "async_retry": (
            "retry handling",
            "retry logic",
            "retry error handling",
            "retry policy",
            "retry policy details are underspecified",
            "retry behavior",
            "retry parameters",
            "retry limits",
            "maximum attempt count",
            "retry attempt count",
            "retries with backoff",
            "retry limits and backoff strategies",
            "retry limits or backoff strategies",
            "error handling and retry mechanisms",
            "undefined error handling and retry mechanisms",
            "retry mechanisms are undefined",
        ),
        "async_idempotency": (
            "idempotency",
            "idempotent processing",
            "duplicate side effects",
        ),
        "async_dead_letter": (
            "dead letter",
            "dead letter handling",
        ),
        "async_failure_status": (
            "failure status",
            "failed status",
            "terminal processing failure",
            "terminal failure state",
        ),
        "result_persistence": (
            "result persistence",
            "persistent storage for processing results",
            "processing results are stored",
        ),
        "result_retrieval": (
            "result retrieval",
            "retrieving processing results",
            "results endpoint",
            "results api",
        ),
    }

    for family, phrases in title_families.items():
        if any(_normalize(phrase) in title for phrase in phrases):
            return family

    # Use the full finding only as a fallback for known issues whose
    # titles are phrased differently.
    text = _normalize(
        " ".join(
            [
                finding.finding,
                finding.evidence,
                finding.recommendation,
            ]
        )
    )

    for family, phrases in title_families.items():
        if any(_normalize(phrase) in text for phrase in phrases):
            return family

    return None


def _same_issue(
    left: ArchitectureReviewFinding,
    right: ArchitectureReviewFinding,
) -> bool:
    if left.category != right.category:
        return False

    left_family = _issue_family(left)
    right_family = _issue_family(right)

    if left_family and right_family:
        return left_family == right_family

    # Conservative fallback for findings without a known issue family.
    left_text = _normalize(left.finding)
    right_text = _normalize(right.finding)

    if not left_text or not right_text:
        return False

    return SequenceMatcher(None, left_text, right_text).ratio() >= 0.82


def _merge_pair(
    left: ArchitectureReviewFinding,
    right: ArchitectureReviewFinding,
) -> ArchitectureReviewFinding:
    """Merge duplicate findings without mixing unrelated evidence."""
    left_rank = _SEVERITY_RANK[left.severity]
    right_rank = _SEVERITY_RANK[right.severity]

    if right_rank > left_rank:
        selected = right
    elif left_rank > right_rank:
        selected = left
    else:
        left_detail = len(left.evidence) + len(left.recommendation)
        right_detail = len(right.evidence) + len(right.recommendation)
        selected = right if right_detail > left_detail else left

    return selected.model_copy()



def merge_review_findings(
    findings: list[ArchitectureReviewFinding],
) -> list[ArchitectureReviewFinding]:
    merged: list[ArchitectureReviewFinding] = []

    for candidate in findings:
        # Clean repeated adjacent words before comparing findings.
        candidate = ArchitectureReviewFinding(
            severity=candidate.severity,
            category=candidate.category,
            finding=_remove_adjacent_duplicate_words(
                candidate.finding
            ),
            evidence=_remove_adjacent_duplicate_words(
                candidate.evidence
            ),
            recommendation=_remove_adjacent_duplicate_words(
                candidate.recommendation
            ),
        )

        # Find an existing finding describing the same issue.
        matching_index = next(
            (
                index
                for index, existing in enumerate(merged)
                if _same_issue(existing, candidate)
            ),
            None,
        )

        if matching_index is None:
            merged.append(candidate)
        else:
            merged[matching_index] = _merge_pair(
                merged[matching_index],
                candidate,
            )

    return merged



def _remove_adjacent_duplicate_words(text: str) -> str:
    return re.sub(
        r"\b([a-z]+(?:-[a-z]+)*)\s+\1\b",
        r"\1",
        text,
        flags=re.IGNORECASE,
    )
