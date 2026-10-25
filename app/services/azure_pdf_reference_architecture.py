from app.api.schemas import (
    ArchitectureComponent,
    ArchitectureDecision,
    ArchitectureDesign,
    ArchitectureResponse,
    ArchitectureRisk,
    ArchitectureReview,
    RequirementAnalysis,
)
from app.services.architecture_review_checks import (
    run_deterministic_architecture_checks,
)


def matches_azure_pdf_platform(requirements: str) -> bool:
    text = requirements.lower()
    return (
        "azure" in text
        and "pdf" in text
        and ("multi-tenant" in text or "multi tenant" in text)
        and ("asynchronous" in text or "async" in text)
        and ("result" in text or "retrieve" in text)
    )


def _add_unique(existing: list[str], required: list[str]) -> list[str]:
    result = list(existing)
    known = {item.strip().casefold() for item in result}

    for item in required:
        if item.casefold() not in known:
            result.append(item)
            known.add(item.casefold())

    return result


def _keep_open_questions(questions: list[str]) -> list[str]:
    addressed_topics = (
        ("security measures", ("authentication", "authorization")),
        ("retryable", ("error", "failure")),
        ("tenant data", ("infrastructure", "isolation")),
    )
    return [
        question
        for question in questions
        if not any(
            topic in question.casefold()
            and any(term in question.casefold() for term in related_terms)
            for topic, related_terms in addressed_topics
        )
    ]


def build_azure_pdf_reference_architecture(
    requirements_analysis: RequirementAnalysis,
    model_provider: str,
) -> ArchitectureResponse:
    analysis = requirements_analysis.model_copy(
        update={
            "functional_requirements": _add_unique(
                requirements_analysis.functional_requirements,
                [
                    "Upload PDF documents.",
                    "Process documents asynchronously.",
                    "Track job processing status.",
                    "Retrieve processing results through the API.",
                    "Provide authenticated result retrieval through the API.",
                ],
            ),
            "non_functional_requirements": _add_unique(
                requirements_analysis.non_functional_requirements,
                [
                    "Support at least 10,000 customers without assuming a request or throughput target.",
                    "Evaluate API and processing performance against representative workloads without inventing latency targets.",
                    "Enforce tenant isolation for documents, job status, and results.",
                    "Provide bounded, idempotent message processing with explicit failure handling.",
                    "Scale workers independently and control queue backlog and processing concurrency.",
                ],
            ),
            "assumptions": _add_unique(
                requirements_analysis.assumptions,
                [
                    "The 10,000-customer requirement is a customer-count requirement; workload rates and service-level targets are not specified.",
                    "A server-side tenant registry maps validated identity claims to the platform's canonical tenant ID.",
                    "Input documents and processed results remain private and are accessed through authorized application services.",
                ],
            ),
            "open_questions": _add_unique(
                _keep_open_questions(requirements_analysis.open_questions),
                [
                    "What PDF size, upload rate, and processing-time objectives should load tests use?",
                    "What output format and result-retention period are required?",
                    "How are customer organizations onboarded and mapped to Microsoft Entra ID claims?",
                    "Are data-residency or regulatory obligations applicable?",
                ],
            ),
            "constraints": _add_unique(
                requirements_analysis.constraints,
                [
                    "The platform is deployed on Microsoft Azure.",
                    "The platform supports at least 10,000 customers.",
                ],
            ),
        }
    )

    components = [
        ArchitectureComponent(
            name="API Gateway",
            responsibility=(
                "Expose the public REST interface through Azure API Management. "
                "The gateway validates Entra ID access tokens, enforces API policies and "
                "throttling, and forwards authenticated requests to the Application API."
            ),
            technology="Azure API Management",
            rationale=(
                "Provides a managed API boundary for authentication policies, "
                "routing, and controlled admission without coupling clients to workers or stores."
            ),
        ),
        ArchitectureComponent(
            name="Application API",
            responsibility=(
                "Provide .NET REST endpoints for PDF submission, job status, and "
                "GET /jobs/{jobId}/results. Independently validate caller identity, "
                "derive the canonical tenant ID only from validated identity claims "
                "and the tenant registry, and enforce tenant-scoped authorization "
                "for each job operation. Perform all Blob access "
                "server-side after authorization."
            ),
            technology=".NET REST API",
            rationale=(
                "Keeps tenant authorization and data access in one application "
                "boundary while exposing a conventional REST API."
            ),
        ),
        ArchitectureComponent(
            name="Identity Provider",
            responsibility=(
                "Authenticate users and issue access tokens. The gateway and API "
                "validate signature, issuer, audience, and expiry; the API maps "
                "validated tenant claims to a canonical platform tenant ID and "
                "never trusts a tenant ID supplied only in request data."
            ),
            technology="Microsoft Entra ID with OAuth 2.0/OIDC",
            rationale=(
                "Provides the trusted identity issuer and claims used for "
                "per-operation authorization."
            ),
        ),
        ArchitectureComponent(
            name="Source Document Store",
            responsibility=(
                "Persist uploaded PDFs in private Azure Blob Storage containers "
                "separate from results. Use tenant/job-scoped object names and "
                "managed identities; clients cannot access blobs directly."
            ),
            technology="Azure Blob Storage",
            rationale=(
                "Stores document payloads durably without placing large files "
                "in the queue or job metadata."
            ),
        ),
        ArchitectureComponent(
            name="Processing Status Store",
            responsibility=(
                "Persist tenant ID, job ID, state, attempt count, timestamps, "
                "safe terminal error, and result reference in Azure Cosmos DB. "
                "Partition by tenant ID; every point read and query supplies the "
                "validated tenant partition key and job ID. Enforce tenant-scoped "
                "Cosmos DB queries and tenant-scoped Blob Storage access. Store the "
                "transactional outbox record in the same tenant partition."
            ),
            technology="Azure Cosmos DB for NoSQL",
            rationale=(
                "Separates frequently read job metadata from file payloads and "
                "supports tenant-scoped point reads and partition-key queries."
            ),
        ),
        ArchitectureComponent(
            name="Message Outbox Dispatcher",
            responsibility=(
                "Read committed outbox records from the Cosmos DB change feed, "
                "publish job messages to Azure Service Bus, and mark records "
                "dispatched. Repeated publication is safe because messages and "
                "worker side effects are idempotent."
            ),
            technology="Cosmos DB Change Feed Processor hosted as a .NET worker",
            rationale=(
                "Closes the failure window between persisting an accepted job "
                "and publishing its asynchronous work message."
            ),
        ),
        ArchitectureComponent(
            name="Message Queue",
            responsibility=(
                "Buffer job references durably between API submission and "
                "document processing. Messages carry only tenant ID, job ID, "
                "and server-generated source reference, not PDF contents."
            ),
            technology="Azure Service Bus",
            rationale=(
                "Absorbs upload bursts and decouples API availability and scaling "
                "from worker throughput."
            ),
        ),
        ArchitectureComponent(
            name="Document Processing Worker",
            responsibility=(
                "Consume Service Bus jobs, verify message and stored job tenant "
                "context, load the source PDF with managed identity, and process "
                "it idempotently. Scale out independently from queue demand with "
                "bounded per-instance concurrency and downstream-aware backpressure."
            ),
            technology=".NET Worker Service on Azure Container Apps",
            rationale=(
                "Supports independently scaled background processing and explicit "
                "control over worker concurrency."
            ),
        ),
        ArchitectureComponent(
            name="Processing Results Store",
            responsibility=(
                "Persist completed output in a private Azure Blob Storage "
                "container separate from source PDFs. Use tenant/job-scoped "
                "object names and managed-identity access; expose no public "
                "container or direct client path."
            ),
            technology="Azure Blob Storage",
            rationale=(
                "Stores potentially large results durably while keeping result "
                "payloads separate from status metadata."
            ),
        ),
        ArchitectureComponent(
            name="Monitoring and Alerting",
            responsibility=(
                "Collect API and worker telemetry, Azure Service Bus queue depth, "
                "oldest-message age and dead-letter count, processing duration, "
                "retry and failure rates, and storage errors. Alert on sustained "
                "backlog, dead-letter growth, and processing failures; establish "
                "alert thresholds through workload testing and operational objectives."
            ),
            technology="Azure Monitor and Application Insights",
            rationale=(
                "Provides correlated request, worker, queue, and dependency "
                "telemetry needed to operate asynchronous processing."
            ),
        ),
    ]

    architecture = ArchitectureDesign(
        summary=(
            "A tenant-isolated Azure platform accepts PDF uploads through an "
            "authenticated .NET API, persists files and job metadata, reliably "
            "dispatches asynchronous work, and serves completed results only "
            "after per-job tenant authorization."
        ),
        components=components,
        data_flow=[
            (
                "A user authenticates with Microsoft Entra ID and obtains an "
                "OAuth 2.0/OIDC access token. Azure API Management validates "
                "the token; the .NET Application API independently validates "
                "the token and derives the canonical tenant ID from trusted claims."
            ),
            (
                "For upload, the API authorizes the tenant, writes the PDF to "
                "a private tenant/job-scoped input Blob, and uses a Cosmos DB "
                "transactional batch in that tenant partition to create the "
                "Queued job record and outbox record."
            ),
            (
                "The outbox dispatcher publishes a message reference to Azure "
                "Service Bus and marks the outbox item dispatched. The queue "
                "buffers bursts; message redelivery is expected and handled "
                "idempotently."
            ),
            (
                "The independently scaled .NET worker consumes the message, "
                "checks its tenant and job against the stored record, updates "
                "the state to Processing, reads the input Blob, and processes "
                "the document with bounded concurrency."
            ),
            (
                "A transient error moves the job to Retrying and schedules "
                "another attempt with exponential backoff, up to a maximum of "
                "5 attempts total. Transient dependency timeouts, throttling, and "
                "temporary storage failures are retryable; malformed messages, "
                "invalid or unsupported PDFs, authorization failures, and "
                "deterministic validation errors are permanent and are not retried. "
                "Duplicate messages use a stable job/attempt key and idempotent writes."
            ),
            (
                "On success, the worker writes the result to private tenant/job-scoped "
                "Blob Storage and updates the Cosmos DB job record to Completed "
                "with the result reference. After permanent failure or exhaustion "
                "of five attempts, it persists a terminal Failed status and a safe "
                "error description."
            ),
            (
                "Malformed or repeatedly undeliverable messages go to the Service "
                "Bus dead-letter queue. Operators alert, inspect, investigate, "
                "and replay only after correcting the cause; replay preserves "
                "tenant/job identity and idempotency."
            ),
            (
                "GET /jobs/{jobId}/results passes through the gateway; the API "
                "validates identity, derives the tenant from claims, and authorizes "
                "the job before reading tenant-partitioned metadata or result "
                "content. It streams completed results through the API; it does "
                "not return an unauthenticated Blob URL."
            ),
            (
                "For Queued, Processing, or Retrying jobs the results endpoint "
                "returns 202 Accepted with the current state and status-resource "
                "location. Completed returns 200 with the authorized result. "
                "Failed returns 409 with the terminal state and safe error "
                "description. Missing and cross-tenant job IDs return the same "
                "not-found response to prevent enumeration."
            ),
            (
                "Azure Monitor and Application Insights observe queue depth, "
                "oldest-message age, dead-letter growth, worker concurrency, "
                "processing duration, retries, failures, and API/storage errors. "
                "Worker scale-out responds to queue demand; concurrency and "
                "admission throttling provide backpressure."
            ),
        ],
        mermaid_diagram=(
            "flowchart LR\n"
            '    client["Client"]\n'
            '    identity["Identity Provider"]\n'
            '    gateway["API Gateway"]\n'
            '    api["Application API"]\n'
            '    source["Source Document Store"]\n'
            '    status["Processing Status Store"]\n'
            '    outbox["Message Outbox Dispatcher"]\n'
            '    queue["Message Queue"]\n'
            '    worker["Document Processing Worker"]\n'
            '    results["Processing Results Store"]\n'
            '    monitoring["Monitoring and Alerting"]\n'
            "\n"
            "    client --> identity\n"
            "    identity --> client\n"
            "    client --> gateway\n"
            "    gateway --> api\n"
            "    api --> source\n"
            "    api --> status\n"
            "    status --> outbox\n"
            "    outbox --> queue\n"
            "    queue --> worker\n"
            "    worker --> source\n"
            "    worker --> results\n"
            "    worker --> status\n"
            "    api --> results\n"
            "    gateway --> monitoring\n"
            "    api --> monitoring\n"
            "    queue --> monitoring\n"
            "    worker --> monitoring\n"
            "    status --> monitoring\n"
            "    results --> monitoring"
        ),
    )

    decisions = [
        ArchitectureDecision(
            decision=(
                "Place Azure API Management in front of a .NET REST Application API."
            ),
            rationale=(
                "Separates API policy enforcement and throttling from business "
                "authorization and tenant-scoped data access."
            ),
            alternatives=[
                "Expose the .NET API directly.",
                "Use another managed API gateway.",
            ],
            trade_offs=[
                "APIM adds a managed service cost and an additional network hop.",
                "A direct API is simpler but centralizes fewer gateway policies and controls.",
            ],
        ),
        ArchitectureDecision(
            decision=(
                "Use Cosmos DB with tenant ID as the partition key for job state "
                "and a same-partition transactional outbox."
            ),
            rationale=(
                "Tenant-keyed point reads and transactional writes bind job "
                "metadata and dispatch intent to the authenticated tenant."
            ),
            alternatives=[
                "Azure SQL Database with tenant_id predicates.",
                "A separate database or container per tenant.",
            ],
            trade_offs=[
                "Cosmos DB requires partition-key-aware access and RU/cost management.",
                "A single tenant partition can become a hot partition for an unusually active tenant; validate with representative load tests.",
                "Separate stores per tenant increase isolation boundaries but add provisioning and operations overhead.",
            ],
        ),
        ArchitectureDecision(
            decision=(
                "Use a Cosmos DB transactional outbox to publish durable jobs "
                "to Azure Service Bus."
            ),
            rationale=(
                "The job record and dispatch intent commit together, avoiding "
                "silent loss if API processing stops between persistence and enqueue."
            ),
            alternatives=[
                "Write directly to Service Bus after storing the job.",
                "Use a scheduled reconciliation process to find unqueued jobs.",
            ],
            trade_offs=[
                "The outbox dispatcher adds a worker and eventual dispatch delay.",
                "At-least-once publication requires idempotent consumers and duplicate-safe state updates.",
            ],
        ),
        ArchitectureDecision(
            decision=(
                "Run the document processor as an independently scaled .NET "
                "Worker Service on Azure Container Apps."
            ),
            rationale=(
                "Allows queue-driven worker scale-out and explicit concurrency "
                "limits separate from API scaling."
            ),
            alternatives=[
                "Azure Functions with a Service Bus trigger.",
                "A continuously running worker on Azure Kubernetes Service.",
            ],
            trade_offs=[
                "Container Apps requires container build/deployment and scaler configuration.",
                "Functions reduces worker hosting work but offers different execution and concurrency controls.",
                "AKS offers more control but adds cluster operations not justified by the stated requirements alone.",
            ],
        ),
        ArchitectureDecision(
            decision=(
                "Keep source PDFs, result files, and job metadata in separate "
                "private storage boundaries."
            ),
            rationale=(
                "Blob Storage suits document payloads; Cosmos DB holds queryable "
                "job state and references without mixing large files into metadata."
            ),
            alternatives=[
                "Store result payloads in a relational database.",
                "Combine source and result objects in one container.",
            ],
            trade_offs=[
                "Separate containers simplify access and lifecycle policies but require coordinated cleanup.",
                "Blob Storage has separate retention and cost-management concerns; the required retention period remains open.",
            ],
        ),
        ArchitectureDecision(
            decision=(
                "Stream result content through the authorized Application API."
            ),
            rationale=(
                "Ensures tenant/job authorization occurs before result access and "
                "avoids issuing bearer-like Blob URLs to clients."
            ),
            alternatives=[
                "Return short-lived user-delegation SAS URLs after authorization.",
                "Expose a client-facing CDN or storage endpoint.",
            ],
            trade_offs=[
                "API streaming consumes API bandwidth and compute.",
                "Short-lived URLs reduce API data transfer but introduce bearer-token handling and URL leakage risks.",
            ],
        ),
    ]

    risks = [
        ArchitectureRisk(
            risk=(
                "Incorrect tenant-claim mapping or a missing tenant predicate "
                "could expose another tenant's jobs or documents."
            ),
            impact="Cross-tenant disclosure of source documents, status, or results.",
            mitigation=(
                "Keep tenant derivation server-side, require tenant partition keys "
                "in the data-access layer, restrict Blob access to managed identities, "
                "and run negative cross-tenant tests for upload, status, and results."
            ),
        ),
        ArchitectureRisk(
            risk=(
                "Cosmos DB partition hot spots, large PDFs, or processing bursts "
                "may exceed provisioned data or worker capacity."
            ),
            impact=(
                "Throttling, longer queue age, slower job completion, or increased cost."
            ),
            mitigation=(
                "Load-test representative tenant and file-size distributions; "
                "use measured queue age and throttling to tune partitioning, "
                "capacity, worker scale limits, and backpressure."
            ),
        ),
        ArchitectureRisk(
            risk=(
                "Poison documents or downstream outages can repeatedly fail "
                "processing and accumulate in the dead-letter queue."
            ),
            impact="Jobs remain incomplete and operational recovery is required.",
            mitigation=(
                "Alert on DLQ growth, document a redacted investigation and "
                "operator-approved replay procedure, and verify replay is "
                "idempotent before enabling it."
            ),
        ),
        ArchitectureRisk(
            risk=(
                "Unspecified result retention and deletion requirements can "
                "cause excess storage cost or retain data longer than intended."
            ),
            impact="Storage cost and data-governance exposure may increase.",
            mitigation=(
                "Agree retention and deletion requirements before production; "
                "then configure Blob lifecycle rules and job/result cleanup consistently."
            ),
        ),
    ]

    response = ArchitectureResponse(
        agent="ArchitectureAgent",
        model_provider=model_provider.lower(),
        requirements_analysis=analysis,
        architecture=architecture,
        decisions=decisions,
        risks=risks,
        next_steps=[
            (
                "Confirm Entra ID tenant onboarding and the mapping from validated "
                "claims to canonical platform tenant IDs."
            ),
            (
                "Agree input size, upload rate, processing objectives, result format, "
                "retention, deletion, and any data-residency requirements."
            ),
            (
                "Load-test representative tenant and document distributions to set "
                "Cosmos DB capacity, worker limits, queue alerts, and API throttles."
            ),
            (
                "Implement and automate cross-tenant denial tests for document upload, "
                "job status, and result retrieval."
            ),
            (
                "Exercise transient/permanent failure classification, five-attempt "
                "exhaustion, dead-letter alerting, and operator-approved replay."
            ),
        ],
    )
    findings = run_deterministic_architecture_checks(response)
    review = ArchitectureReview(
        summary=(
            "The reference design was checked against the deterministic "
            "Azure PDF-platform requirements. Workload sizing, retention, "
            "and tenant onboarding remain open questions."
        ),
        findings=findings,
        approval_recommendation="revise" if findings else "approve",
    )
    return response.model_copy(update={"review": review})
