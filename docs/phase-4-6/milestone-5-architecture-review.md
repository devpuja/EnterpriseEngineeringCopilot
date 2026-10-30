# Phase 4.6 Milestone 5: Architecture Review

## Objective and scope

Milestone 5 consumes an `ArchitectureSynthesisResult` and optionally a matching
`RepositoryAnalysisResult`. It produces a deterministic, structured repository architecture
review without repository discovery, static re-analysis, synthesis regeneration, report export,
LLM calls, agent orchestration, HTTP endpoints, or deployment assumptions.

## Package structure

- `app/repository/review/models.py` - review findings, strengths, recommendations, outcomes, and result contracts.
- `app/repository/review/contracts.py` - `ArchitectureReviewContract`.
- `app/repository/review/deterministic_checks.py` - evidence-driven structural and relationship checks.
- `app/repository/review/architecture_review_service.py` - review orchestration, outcome calculation, and traceability.
- `app/repository/review/__init__.py` - public package exports.

## Input and output

`ArchitectureReviewService.review(synthesis, analysis=None)` accepts the existing synthesis model
and an optional matching analysis result. A mismatched analysis is ignored with a warning.

`ArchitectureReviewResult` contains the synthesis and available analysis IDs, repository identity,
summary, overall outcome, findings, evidence-supported strengths, priority recommendations,
warnings, limitations, and review metadata. It does not duplicate the synthesis model.

## Review categories and rules

Rules cover:

- Architecture structure and responsibility clarity.
- Unresolved or inferred dependencies and circular dependency paths.
- Dependency concentration.
- External integration evidence completeness.
- Data-flow endpoint validity and relationship consistency.
- Missing synthesis evidence and incomplete analysis limitations.

The deterministic rules use stable SHA-1-derived finding IDs, preserve original evidence IDs,
avoid duplicate findings, and only treat static graph relationships as dependency evidence.

## Finding statuses

- `confirmed`: supported by a preserved relationship/component/evidence path.
- `inferred`: static evidence suggests an issue but does not establish a stronger conclusion.
- `needs_investigation`: evidence is missing, inconsistent, or insufficient for confirmation.

Every confirmed finding generated from component, relationship, integration, or data-flow evidence
must have a valid supporting evidence reference. Missing static evidence is never interpreted as
proof that a runtime control is absent.

## Evidence and confidence

The service validates synthesis evidence references against the optional analysis evidence and the
synthesis's own referenced IDs. It does not invent components or evidence. Component confidence and
relationship/data-flow confidence are preserved when available. Findings with no valid evidence use
low confidence or an investigation status. Synthesis and analysis warnings/limitations remain visible
in the result.

## Severity and outcome

Severity values are `critical`, `high`, `medium`, `low`, and `informational`.

Outcome decision rules:

- `significant_risks`: one confirmed critical finding, or at least two confirmed high findings.
- `needs_investigation`: investigation findings exist without confirmed critical/high findings.
- `improvements_recommended`: confirmed/inferred findings remain actionable.
- `healthy`: no actionable findings remain.

The static review does not declare a repository production-ready.

## Recommendations and trade-offs

Every finding includes an actionable recommendation, and recommendations may include expected
benefits, trade-offs, implementation considerations, priority, and implementation effort. Priority
recommendations are derived only from actual findings; the implementation does not generate generic
or system-wide redesign advice.

Positive observations are emitted only when components, relationships, or data flows have valid,
preserved evidence.

## Limitations

The review does not observe runtime behavior, deployment topology, execution order, network traffic,
database contents, or production controls. Inferred and incomplete evidence remains explicitly
qualified. Static absence is not treated as absence of security, reliability, or scalability controls.

## Tests

Commands run in the project virtual environment with plugin autoload disabled:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
.\.venv\Scripts\python.exe -m pytest tests/repository/visualization/test_milestone5_architecture_review.py -q
.\.venv\Scripts\python.exe -m pytest tests/repository/analysis tests/repository/visualization tests/repository/reporting tests/test_phase2_review_regressions.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

Actual results:

- Milestone 5 focused tests: 7 passed.
- Repository and Phase 2 regression set: 50 passed.
- Complete pytest suite: 214 passed, 2 skipped.
