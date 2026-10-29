# EnterpriseEngineeringCopilot
AI assistant for software architects, senior developers, and engineering teams.

## Model configuration

Set `APP_NAME`, `APP_ENV`, `LOG_LEVEL`, `MODEL_PROVIDER`, `OPENAI_API_KEY`, and
`OPENAI_MODEL` in `.env`. The retained Microsoft Agent Framework OpenAI adapter
uses the configured OpenAI model; no user login is required. Copy `.env.example`
to `.env`, provide an OpenAI API key, then start the FastAPI application with
`uvicorn main:app --reload`.

Enterprise Software Architecture & Engineering Copilot
│
├── Architecture
├── Phase 1 – Foundation
├── Phase 2 – Multi-Agent
├── Phase 3 – RAG
├── Phase 4 – MCP & Tools
├── Phase 5 – Enterprise Security
├── Phase 6 – Observability & Evaluation
└── Phase 7 – Production/Azure


Phase 1 — Foundation
Baseline completed
FastAPI, Pydantic schemas, model abstraction, structured outputs, error handling, logging, tests, Mermaid validation, and architecture-quality heuristics.

Follow-up: Verify compatibility with the chosen current MAF version before adding more capabilities.


Phase 2 — MAF Multi-Agent Architecture
Modernize the agent workflow using MAF's supported workflow APIs, typed data handoffs, independent review, controlled revision, workflow events, and failure handling.
- Requirements Analysis Agent
- Architecture Design Agent
- Architecture Review Agent
- MAF workflow orchestration
- Agent sessions, context management, and appropriate memory patterns
- Unit and workflow integration tests


Phase 3 — Local RAG and Enterprise Knowledge

Status: Implemented. Phase 3 provides local PDF/TXT ingestion, OpenAI embeddings, persistent ChromaDB retrieval, document metadata, and grounded MAF answer generation.

Ground architecture recommendations and user questions in authoritative local technical information.
- Document ingestion, parsing, chunking, metadata, and embeddings
- Vector search, hybrid search, filters, and reranking
- Azure AI Search as the primary Azure retrieval option
- Source citations and retrieval-grounded responses
- RAG evaluation: retrieval relevance, groundedness, and answer quality
- Knowledge-base versioning and document access controls


Phase 4 — MCP, Tools, and Agent Patterns

Allow agents to use controlled engineering capabilities rather than only generate text.
- Function/tool calling and typed tool contracts
- Build an MCP server and connect an MCP client
- Tool discovery, invocation, authentication, and error handling
- Agent-as-tool and appropriate multi-agent delegation patterns
- Human approval for consequential actions
- Safe tools for architecture analysis, repository inspection, and document generation

## Implementation roadmap ##

Phase 4.1 — Tool contracts and function calling
Define a small set of typed tools using the existing MAF conventions.
- Tool names, descriptions, input schemas, and output schemas.
- Argument validation and predictable error responses.
- Tool registration and invocation.
- Tests for valid, invalid, and failed calls.
Outcome: an agent can select and invoke a supported function safely.

Phase 4.2 — Build an MCP server
Expose selected engineering tools through the Model Context Protocol (MCP).
- Understand MCP tools, schemas, and responses.
- Implement a server using a compatible Python MCP SDK.
- Expose a small, controlled set of capabilities.
- Handle tool errors and server lifecycle.
Outcome: tools can be discovered and used through a standard protocol rather than only through application-specific function registrations.

Phase 4.3 — MCP client integration
Connect the existing copilot to the MCP server.
- Establish and close client sessions.
- Discover available tools dynamically.
- Map tool schemas into the agent's tool-calling workflow.
- Invoke tools and return structured results.
- Handle connection failures, timeouts, and unavailable tools.
Outcome: the copilot can discover and use MCP tools without hard-coding every tool into the orchestration logic.

Phase 4.4 — Controlled tool execution
Add safeguards to the tool execution layer.
- Allowlist permitted tools.
- Validate arguments and restrict file paths.
- Set timeouts and execution limits.
- Return structured errors without exposing secrets.
- Define connection trust and credential handling for MCP.
- Require human approval for consequential or modifying actions.
Outcome: tools are constrained by explicit application policies, not solely by the LLM's judgment.

Phase 4.5 — Agent-as-tool and delegation
Integrate specialized agents into controlled workflows.
- Expose a specialized agent as a callable capability where appropriate.
- Delegate repository analysis or architecture review to the relevant agent.
- Keep the orchestrator responsible for the overall workflow.
- Define clear inputs, outputs, and termination conditions.
- Prevent unnecessary agent-to-agent calls and loops.
Outcome: a multi-agent workflow with clear responsibilities rather than a collection of agents that call one another unpredictably.

Phase 4.6 — Engineering tools and end-to-end workflow
Implement practical tools that use the existing project capabilities.
- Repository inspection: list and read files from an explicitly allowed workspace.
- Architecture analysis: inspect source code and report structural findings.
- Document generation: produce an architecture review or design report using existing generation capabilities.
- Human approval: request approval before modifying files or performing other consequential actions.
- End-to-end testing: verify tool discovery, delegation, output quality, and error handling.
Outcome: a working engineering copilot workflow that delivers a tangible artifact, not just a text response.


<!-- Phase 5 — Enterprise Security and Governance

Make the copilot safe for enterprise workloads and sensitive engineering data.
- Microsoft Entra ID, authentication, authorization, and RBAC
- Tenant isolation and document-level access control
- Managed identity and Azure Key Vault
- Prompt injection and indirect prompt injection defenses
- Input validation, output validation, and tool permission boundaries
- Content safety, sensitive-data protection, audit logs, and threat modeling
- Network isolation and least-privilege access where required -->

Phase 5 — Enterprise Security
Next: establish the security architecture and implement safeguards incrementally.

Starting

1. What will we build?
The goal is to move the Copilot from a locally functioning multi-agent application toward a system with enterprise-grade security controls.

5.1 — Authentication
Establish how callers prove their identity before accessing protected APIs.

5.2 — Authorization and access control
Define which users or roles can invoke APIs, use tools, and approve actions.

5.3 — Secure tool and MCP execution
Enforce tool permissions, validate inputs, and prevent unauthorized or unsafe operations.

5.4 — Approval security and audit trail
Connect approval decisions to authenticated reviewers and record security-relevant actions.

5.5 — Secrets and sensitive-data protection
Prevent credentials, sensitive information, and internal errors from leaking through logs or API responses.


Phase 6 — Observability, Evaluation, LLMOps and GenAIOps

Measure quality and operate the AI lifecycle reliably, not just monitor whether the API is running.
- Distributed tracing across agents, models, tools, and retrieval
- OpenTelemetry, Azure Monitor, and Application Insights
- Token consumption, latency, model usage, and cost per workflow
- Evaluation datasets, quality metrics, safety evaluation, and regression tests
- Model and prompt versioning, configuration management, and release comparisons
- Continuous evaluation and evaluation gates in CI/CD
- Production feedback, drift and quality monitoring, incident response
- Microsoft Foundry evaluation and observability capabilities where appropriate


Phase 7 — Microsoft Foundry, Azure Deployment and Production (not implemented)

Deploy, secure, scale, and operate the end-to-end solution.
- Microsoft Foundry projects, model catalog, model deployments, and endpoint configuration
- Evaluate when to use Foundry-hosted agent capabilities versus an application-hosted MAF workflow
- Deploy the FastAPI/MAF application to an appropriate Azure hosting service
- Azure AI Search, Blob Storage, and messaging or database services where justified
- Managed identity, Key Vault, networking, and secrets
- Docker, Azure Container Registry, CI/CD, and infrastructure as code with Bicep
- Autoscaling, health checks, resiliency, backups, disaster recovery, and cost budgets
- Production release strategy, runbooks, SLOs, and operational readiness

## Phase 3 — local RAG implementation

Phase 3 adds a local document-grounded question-answering pipeline without Azure or authentication dependencies.

### Components

- `app/services/document_ingestion.py` validates files, extracts PDF/TXT content, normalizes text, chunks text, and creates stable IDs.
- `app/services/embedding_service.py` defines the embedding interface and implements bounded-retry OpenAI embeddings.
- `app/services/vector_store.py` owns ChromaDB persistence, insertion, similarity search, replacement, and deletion.
- `app/services/document_repository.py` stores document lifecycle metadata in SQLite.
- `app/services/rag_service.py` orchestrates ingestion, context assembly, retrieval, and the existing MAF answer client.
- `app/api/rag.py` exposes upload, listing, retrieval, deletion, and query endpoints.

### Ingestion flow

1. `POST /api/v1/rag/documents` receives a PDF or TXT upload.
2. The API validates size, extension, and media type, then rejects empty or unsupported content clearly.
3. PDF pages are extracted with page numbers; TXT files are decoded as UTF-8.
4. Text is normalized and split with configurable chunk size and overlap.
5. OpenAI embeddings are generated in a worker batch.
6. ChromaDB removes old chunks for the same stable document ID and inserts replacement chunks.
7. SQLite records the filename, document ID, status, chunk count, timestamps, and failures.

### Query flow

1. `POST /api/v1/rag/query` validates the natural-language question.
2. The question is embedded with `OPENAI_EMBEDDING_MODEL`.
3. ChromaDB retrieves the configured top-k chunks.
4. The pipeline creates a bounded context and citations with filename, document ID, chunk, and PDF page when available.
5. The MAF-based RAG answer agent receives the question and context in a prompt that treats document text as untrusted evidence.
6. If retrieval is empty, the API returns an explicit non-grounded answer without calling the generation model.

### Configuration

Copy `.env.example` to `.env`. Required RAG behavior:

- `OPENAI_API_KEY`: required only when embeddings or model answers are requested.
- `OPENAI_EMBEDDING_MODEL`: defaults to `text-embedding-3-small`.
- `CHROMA_PERSIST_DIRECTORY`: local persistent ChromaDB directory, default `rag_data/chroma`.
- `CHROMA_COLLECTION_NAME`: collection name.
- `DOCUMENT_STORAGE_DIRECTORY`: uploaded document directory.
- `RAG_METADATA_DATABASE`: SQLite document metadata database.
- `MAX_UPLOAD_SIZE_BYTES`, `CHUNK_SIZE`, and `CHUNK_OVERLAP`: ingestion limits.
- `RAG_TOP_K` and `RAG_CONTEXT_CHAR_LIMIT`: retrieval bounds.
- `RAG_ADJACENT_CHUNK_RADIUS`: same-document neighboring chunk expansion radius.
- `RAG_SOURCE_EXCERPT_CHAR_LIMIT`: maximum source preview length; each source also reports `excerpt_truncated`.
- `EMBEDDING_TIMEOUT_SECONDS` and `EMBEDDING_MAX_RETRIES`: provider reliability limits.

RAG answers expose both the model-reported `model_grounded` flag and a deterministic `verification_status` (`verified`, `unverified`, or `inconclusive`). The compatibility `grounded` field is conservative: it is true only for deterministic verification success, never from model self-reporting or source presence alone.

Generating embeddings incurs OpenAI API usage charges. No live API call is made during application startup.

### API examples

Upload a document:

```text
POST /api/v1/rag/documents
Content-Type: multipart/form-data
```

Then select `file` in Swagger (`/docs`).

Ask a grounded question:

```json
POST /api/v1/rag/query
{
  "question": "What tenant isolation controls are documented?",
  "top_k": 5
}
```

List documents with `GET /api/v1/rag/documents`, fetch one with `GET /api/v1/rag/documents/{document_id}`, and delete one with `DELETE /api/v1/rag/documents/{document_id}`.

### Developer walkthrough

1. Start at the document endpoint to see validation and worker-thread boundaries.
2. Follow `RAGService.ingest` into extraction, embeddings, ChromaDB replacement, and SQLite metadata.
3. Follow `RAGService.answer` into question embedding, similarity search, bounded context assembly, and the MAF answer agent.
4. Inspect `RAGSource` construction to understand how filename, page, chunk, and document IDs become citations.
5. Use the deterministic embedding provider and temporary directories in tests to verify behavior without live OpenAI calls.

Chunk size trades contextual completeness against retrieval precision. Overlap reduces boundary losses but duplicates text and storage. Top-k controls recall but also context noise and token cost. Replacing by stable document ID prevents stale vector chunks while SQLite coordinates lifecycle metadata.

Common interview questions include: why embeddings are isolated behind an interface, how partial ingestion failures are cleaned up, why metadata and vector stores are separate repositories, and how prompt injection from uploaded documents is mitigated.

### Local data and reset

Documents and generated local data are stored beneath `rag_data/` by default. Reset local RAG state by stopping the application and removing `rag_data/`. `.gitignore` excludes this directory.

### Security and limitations

Uploaded document text is treated as untrusted. The answer prompt explicitly rejects document instructions and reports unsupported answers. ChromaDB and metadata are local to the process environment; this implementation does not provide authentication, Azure integration, cross-user authorization, encryption-at-rest services, or managed backups.