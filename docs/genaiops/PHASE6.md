# Phase 6: GenAIOps

## Milestone status

| Milestone | Status |
|---|---|
| 6.1 Structured logging | Implemented and locally verified |
| 6.2 Tracing | Implemented and locally verified |
| 6.3 Usage, cost, metrics | Implemented and locally verified |
| 6.4 Evaluation framework | Implemented and locally verified |
| 6.5 Agent/workflow evaluation | Implemented and locally verified |
| 6.6 RAG evaluation | Implemented and locally verified |
| 6.7 Quality gates | Implemented and locally verified |
| 6.8 Operational integration | Implemented and locally verified |

## Structured logging

`LOG_FORMAT=text` preserves readable local output; `json` emits structured
events. `LOG_LEVEL` accepts DEBUG, INFO, WARNING, ERROR, CRITICAL. API requests
return `X-Request-ID` and `X-Correlation-ID`. Client correlation values are
restricted to 64 ASCII letters, digits, underscores or hyphens; invalid values
are replaced. Context is propagated through async tasks and worker threads.
Logs include UTC timestamps, components, events and safe operation metadata.
Prompts, answers, document/source content and credentials are not telemetry
fields. Exception diagnostics retain category and function/line information,
not exception messages or local variables. Phase 5 redaction is reused.

## Tracing

Set `TELEMETRY_ENABLED=true` to enable application and native MAF spans.
`TELEMETRY_EXPORTER=none` needs no backend; `console` prints safe spans;
`otlp` sends to `TELEMETRY_OTLP_ENDPOINT` (include `/v1/traces`).
`TELEMETRY_SAMPLE_RATIO` is 0-1 with parent-based sampling. Export queues
are bounded (512 spans); telemetry failures are logged and do not replace
business results. Sensitive model/message telemetry is explicitly disabled;
export strips unknown attributes, message events, links and status descriptions.
Async and worker-thread operations retain the parent trace.
Incoming W3C `traceparent`/`tracestate` is extracted with bounded header lengths;
baggage is not accepted. HTTP error responses and failure-shaped export results
produce failed observations/spans, not success-shaped telemetry.

With tracing enabled, MCP calls propagate W3C headers through the Streamable
HTTP transport. The local MCP entry point serves stateless Streamable HTTP on
loopback port 8001 with request instrumentation and its native lifespan.
Disabled telemetry preserves the existing client transport. Discovery and
read-only tools retain their existing contracts; credentials are not forwarded.

The repository workflow is deterministic: retrieval -> analysis -> visualization
-> synthesis -> review -> report. The separate MAF workflow executes requirements
-> design -> review -> bounded revision -> finalize. Neither is artificially
connected to RAG or agents that did not execute.

Verification: 6.1 focused regression **58 passed, 2 skipped**.
6.2 tracing/workflow regression: **49 passed, 2 skipped**.

## Usage, metrics and costs

Chat middleware captures client responses rather than aggregate agent results;
embedding responses use the same extraction service. Missing usage is explicit.
Embedding output tokens are zero because vectors are not generated text.
`USAGE_ENABLED` controls capture. `MODEL_PRICING` is an operator-configured JSON
array with provider, model, input_per_million, output_per_million,
cached_input_per_million (optional), currency and version. No prices ship by
default. Costs use Decimal and are estimates, never invoices; missing usage,
unknown pricing or unavailable cache accounting produces unavailable cost.

Histograms record durations; counters record operations, tokens and observed
application retries. A 1000-record process-local rolling buffer holds content-free
observations associated with request/workflow/agent and owner. Its summaries
are incomplete after eviction/restart; no p95/p99 claims are made.
Observations are validated typed records. Exported metric attributes use an
allowlist; request IDs, owner IDs and arbitrary source labels are not metric
dimensions.

6.3 focused regression: **67 passed**.

## Deterministic evaluation

Versioned datasets define inputs, observed outputs, references, criteria and
source judgments. Runs report passed/failed/not-applicable/error separately;
missing references are not successful scores. Supported metrics are normalized
matching, required fields/phrases, existing application schemas and source IDs.
These do not measure universal semantic correctness or safety.

Run offline without paid model calls:

```powershell
.\.venv\Scripts\python.exe -m app.evaluation tests\fixtures\genaiops\responses-v1.json
```

Use `--output <path>` for a local JSON report. Exit code is nonzero for failures
or evaluator errors. Output summaries exclude original content. Only synthetic
or approved sanitized datasets should be evaluated; datasets themselves may
contain text. No LLM-as-judge integration is claimed.

6.4 focused regression: **15 passed**; response dataset **3/3 passed**.

## Agent and workflow evaluation

`evaluate_target` accepts an injected async agent/workflow executor, preserving
provider/model metadata. `evaluate_stages` compares actually observed order
with required stages. Versioned synthetic workflow cases exercise real
repository services and all four exporters; agent fixtures pass through real
agent parsing. Failure scenarios include partial analysis, inaccessible inputs,
provider timeout, malformed output, source-ID mismatch and export failure.
Fixture tests verify contracts and controls, not live LLM response quality.
The Requirements/Architecture/Review agents, native MAF revision workflow and
delegation coordinator retain their existing responsibilities.

6.5 focused regression: **16 passed**, including **12/12 workflow scenarios**.
Workflow fixtures require the injected executor used by the tests; they are
not live-agent datasets for the default response CLI.

## RAG evaluation

`RAGService.retrieve` returns both ranked semantic hits and expanded context,
preserving normal answer behavior and ownership filters. Evaluate rankings
before context ordering. The nine-case synthetic dataset covers obvious,
multi-chunk/document, partial, empty, ambiguous, missing-metadata, conflicting
and insufficient-evidence cases. Grades 0-3 are explicit judgments, not invented
model scores. Unjudged results or missing labels make metrics unavailable.
Empty relevant sets leave recall/MRR/NDCG undefined. Precision/recall count
grades above zero; NDCG uses graded gain `2^grade - 1`.

Grounding reuses the conservative existing validator. Lexical support is not
proof of semantic correctness; conflicting evidence is not resolved by NDCG.

6.6 focused regression: **55 passed, 2 skipped**.
Prerecorded rankings have no invented retrieval latency; callback-based
evaluation measures the actual retrieval duration.

## Quality gates and failures

Report validity reuses the canonical validator and preserves its exceptions.
Diagram validity and RAG grounding emit advisory outcomes by default.
`DIAGRAM_REQUIRE_VALID=true` rejects structurally invalid generated repository
diagrams. `RAG_REQUIRE_VERIFIED=true` rejects generated answers that fail
conservative evidence verification. These opt-ins can reject useful paraphrases
and are not universal hallucination detectors. Missing retrieval still returns
the existing explicit insufficient-evidence response.

Embedding retries are bounded by `EMBEDDING_MAX_RETRIES` with SDK retries
disabled: network/timeouts/rate limits/server errors retry; permanent errors
fail without retry. Existing diagram repair (one attempt) and MAF architecture
revision (two revisions) remain bounded. MCP timeout/allowlist/result validation
and ownership controls are unchanged.

6.7 focused regression: **151 passed, 2 skipped**.

## Operational inspection

`GET /api/v1/operations/summary?minutes=60` requires a recognized application
role, including ReadOnly. Every caller (also Administrator) sees only their
own observations. It returns sample counts, mean/max durations, failures,
reported token totals, unavailable usage/cost counts, estimated subtotals
separated by currency, observed retries and evaluation/quality counts.
The shared 1000-record process-local buffer is bounded, not durable or complete;
SDK retries not observed by application middleware are not invented.
Standalone CLI evaluations run without an API owner and are not exposed to users.
No raw prompts, answers, dataset cases, documents, paths or owner IDs are returned.

### Local walkthrough

1. Keep the existing Entra issuer/audience/JWKS/Swagger configuration.
2. Set `LOG_FORMAT=json`, optionally `TELEMETRY_ENABLED=true` and
   `TELEMETRY_EXPORTER=console`. Restart Uvicorn.
3. Sign in at `http://localhost:8000/docs`, create a repository report, export
   and download it. Inspect correlated events and actual child spans.
4. Query the operations summary as the same user. Another user's results are
   intentionally invisible. No model prices means unavailable estimates.
5. Run the offline datasets/tests before using opt-in strict quality gates.

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_workflow_evaluation.py tests\test_rag_evaluation.py tests\test_operations_api.py tests\test_telemetry_integration.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

### Final verification

- Pre-Phase 6 baseline: **338 passed, 5 skipped**.
- Final regression: **366 passed, 5 skipped**.
- Final focused hardening checks: **25 passed**.
- Python compilation and `git diff --check` passed.
- Isolated enabled-telemetry integration verifies HTTP/JWT, repository stages,
  each exporter, artifact downloads, native MAF usage, metadata-only export,
  and real loopback MCP trace continuity. Provider HTTP is fully mocked; the
  scoped MCP server is stopped by the test.
- Offline response dataset: **3/3 passed**. Workflow evaluation exercises
  **12/12 synthetic scenarios**. These are local contract tests, not live-model
  quality benchmarks.
- No configured lint/type-check runner was found; no such result is claimed.

The existing environment has an unrelated dependency conflict:
`agent-framework-foundry-hosting 1.0.0b261015` requires `mcp<2,>=1.24.0`,
while installed MCP is `2.3.0`. Foundry hosting is not a Phase 6 dependency;
resolve that optional integration separately before using it. The full local
application regression passes; this does not make that environment conflict
production-ready.

### Failure behavior

| Failure | Expected behavior |
|---|---|
| Telemetry exporter unavailable | Bounded background export; warning; workflow unchanged |
| Model provider failure/timeout | Existing safe API error; failed operation observation |
| Missing usage/unknown pricing | Explicit unavailable data, not fabricated zeros/cost |
| RAG retrieval failure | Existing error; failed retrieval span/observation |
| MCP timeout | Existing bounded timeout and safe API error |
| Agent failure | Stops/propagates through existing workflow; failed observation |
| Evaluator failure | Error result with category, no response mutation |
| Invalid output | Existing schema/report failure or configured hard gate |
| Export failure | Existing failed export/cleanup behavior; failed observation |

### Phase 7 backlog

- Azure Application Insights / Azure Monitor and production OTLP routing.
- Durable, tamper-resistant audit/approval/evaluation retention.
- Shared transactional ownership/state for multiple workers.
- Managed identity and Key Vault/platform secret references.
- HTTPS, protected deployment, rate limiting and exporter egress controls.
- Alerting, operational budgets, real pricing review, load/latency benchmarks.
- Backups, recovery, scaling and production reliability.

Local telemetry and fixture evaluation are implemented, not evidence of live
model semantic quality, universal prompt-injection resistance or production
Azure integration. No Azure deployment was performed.

Final status: milestones 6.1-6.8 are complete for local single-process operation.
Production readiness remains Phase 7 and is not implied by passing fixture tests.
