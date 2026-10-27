# EnterpriseEngineeringCopilot
AI assistant for software architects, senior developers, and engineering teams.

## Model configuration

Set `APP_NAME`, `APP_ENV`, `LOG_LEVEL`, and `MODEL_PROVIDER` in `.env`.
Only the selected chat provider's configuration is required when creating a model client:

| `MODEL_PROVIDER` | Required settings |
| --- | --- |
| `openai` | `OPENAI_API_KEY`, `OPENAI_MODEL` |
| `azure_openai` | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_CHAT_DEPLOYMENT` |
| `foundry` | `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_MODEL` |

Provider names are case-insensitive. Settings for inactive providers can be omitted;
for example, Foundry does not require OpenAI configuration.
Azure OpenAI uses `DefaultAzureCredential` when `AZURE_OPENAI_API_KEY` is omitted.
Foundry uses the Azure CLI identity (`az login`). Embeddings additionally require
`FOUNDRY_EMBEDDING_MODEL` and the OpenAI-compatible
`FOUNDRY_OPENAI_ENDPOINT`.

`RAG_BACKEND` is exposed as `settings.rag_backend` and defaults to `memory`.
Backend selection and tenant checks both use this setting, loaded at startup
from `.env` with process environment variables taking precedence. Restart the
application after changing it. Supported values are `memory` and `azure`.

RAG adapters use the same settings object for search, storage, embeddings, and
chunking. Environment variable names map to lowercase attributes, for example
`AZURE_SEARCH_ENDPOINT` becomes `settings.azure_search_endpoint`.

| Environment setting | Default / requirement |
| --- | --- |
| `AZURE_SEARCH_ENDPOINT` | Required for Azure search |
| `AZURE_SEARCH_INDEX_NAME` | `engineering-knowledge-v2` |
| `AZURE_SEARCH_API_KEY` | Optional; otherwise uses `DefaultAzureCredential` |
| `AZURE_STORAGE_ACCOUNT_URL` | Required unless a connection string is provided |
| `AZURE_STORAGE_CONTAINER` | `engineering-documents` |
| `AZURE_STORAGE_CONNECTION_STRING` | Optional alternative to identity authentication |
| `RAG_EMBEDDING_DIMENSIONS` | `1536`; must match embedding vectors and the search index |
| `RAG_CHUNK_SIZE` / `RAG_CHUNK_OVERLAP` | `1200` / `150` for the Azure backend |

The legacy Azure OpenAI embedding adapter additionally uses
`AZURE_OPENAI_EMBEDDING_DEPLOYMENT`. Azure-specific values can remain unset
when using the memory backend; required-value checks run when creating the
corresponding adapter.

RAG API unit tests explicitly select the `memory` backend and use fake services,
independent of local `RAG_BACKEND` configuration. Azure-mode tests verify that
requests without trusted tenant context are rejected. In the application,
`RAG_BACKEND=azure` requires middleware-provided tenant context; sending
`X-Tenant-ID` alone is not sufficient.

Entra middleware reads the shared settings loaded from `.env`:
`ENTRA_TENANT_ID` is the directory tenant ID, `ENTRA_API_CLIENT_ID` is the API
app registration's client ID (the expected v2 token audience), and
`ENTRA_REQUIRED_SCOPE` defaults to `access_as_user`.
Azure RAG requests need a bearer access token with the required delegated scope.
Missing authentication configuration returns 503 and logs a configuration error;
missing or invalid tokens return 401, and missing scope returns 403.
Memory-mode RAG and public health routes do not require Entra configuration.
Restart the application after changing these values. No client secret is needed
by this middleware to validate incoming tokens.

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


Phase 3 — RAG and Enterprise Knowledge

Ground architecture recommendations in authoritative technical and organizational information.
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


Phase 5 — Enterprise Security and Governance

Make the copilot safe for enterprise workloads and sensitive engineering data.
- Microsoft Entra ID, authentication, authorization, and RBAC
- Tenant isolation and document-level access control
- Managed identity and Azure Key Vault
- Prompt injection and indirect prompt injection defenses
- Input validation, output validation, and tool permission boundaries
- Content safety, sensitive-data protection, audit logs, and threat modeling
- Network isolation and least-privilege access where required


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


Phase 7 — Microsoft Foundry, Azure Deployment and Production

Deploy, secure, scale, and operate the end-to-end solution.
- Microsoft Foundry projects, model catalog, model deployments, and endpoint configuration
- Evaluate when to use Foundry-hosted agent capabilities versus an application-hosted MAF workflow
- Deploy the FastAPI/MAF application to an appropriate Azure hosting service
- Azure AI Search, Blob Storage, and messaging or database services where justified
- Managed identity, Key Vault, networking, and secrets
- Docker, Azure Container Registry, CI/CD, and infrastructure as code with Bicep
- Autoscaling, health checks, resiliency, backups, disaster recovery, and cost budgets
- Production release strategy, runbooks, SLOs, and operational readiness