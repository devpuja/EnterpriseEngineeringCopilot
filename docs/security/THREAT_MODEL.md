# Security Threat Model

This STRIDE-oriented model covers the current local, single-process application.

## Assets and trust boundaries

- Assets: model credentials, validated identities, repository source, uploaded
  documents and embeddings, architecture reports, exported artifacts, and
  approval records.
- Trust boundaries: caller to FastAPI; FastAPI to local files/SQLite/Chroma;
  application to the configured model provider; application to the loopback
  MCP server; and generated output to downloaded artifacts.
- Threat actors: unauthenticated callers, authenticated users with limited
  roles, malicious repository/document authors, compromised model or MCP
  responses, and local deployment operators.

## Threats and controls

| STRIDE | Threat | Controls | Residual risk |
|---|---|---|---|
| Spoofing | Forged, expired, wrong-issuer or wrong-audience bearer tokens | RS256 JWKS signature verification; required issuer, audience, time, and subject claims | Identity provider and JWKS endpoint availability are external dependencies |
| Tampering | Caller changes reviewer identity or artifact paths | Reviewer derived from token; UUID artifact IDs; canonical managed paths; overwrite-safe file creation | In-memory registries do not coordinate across workers |
| Repudiation | User denies approval or sensitive operation | Structured security event logging with pseudonymous actor/resource IDs | Audit events are not durable or tamper-evident |
| Information disclosure | Cross-user report/document access or credential logging | Owner checks at service boundaries; owner-filtered Chroma retrieval; secret redaction; safe API errors | Local storage and backups need deployment-level access controls and encryption |
| Denial of service | Large uploads, repositories, or slow MCP/model calls | Upload/repository limits, bounded context, MCP timeout, provider timeouts | No global request rate limiting or workload queue |
| Elevation of privilege | Read-only or ordinary user invokes privileged operations | Central role dependencies; roles accepted only from validated token claims | Role assignment and token issuance remain identity-provider responsibilities |

## Malicious content and prompt injection

Repository files, uploaded documents, retrieved chunks, diagrams, and MCP
responses are untrusted data. RAG prompts explicitly preserve the instruction
boundary, and agent/tool permissions are independently enforced by application
code. Retrieved document queries are owner-filtered; the RAG agent is not given
filesystem or arbitrary command tools. Prompt text is a defense-in-depth aid,
not an authorization boundary.

## Known residual risks

- Configure the identity provider's role assignments and audience correctly.
- Use a private, least-privilege network and restrict the configured local
  repository roots.
- Protect local database/vector/artifact volumes, logs, backups, and host
  credentials.
- Use durable shared ownership storage before enabling multiple workers.
- Integrate durable audit retention, encryption at rest, rate limits, and
  managed secrets before production deployment.
- The MCP server is loopback-only by default and has no independent user
  authentication; do not expose it directly on an untrusted network.
