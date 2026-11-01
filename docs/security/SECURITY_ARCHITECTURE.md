# Security Architecture

## Trust boundaries and request flow

Application calls follow this boundary sequence:

1. `/` and `/health` are public and return no private resource data.
2. Every `/api/v1` operation requires an HTTP Bearer token. The API verifies
   the signature using the configured HTTPS JWKS endpoint and only accepts
   RS256. It also checks `iss`, `aud`, `exp`, `iat`, and `sub`.
3. Authorization maps only known `roles` claims to the application's
   Administrator, Architect, Developer, Analyst, and ReadOnly roles.    Owner IDs are pseudonymous hashes derived from the validated issuer and
   subject, never request bodies.
4. Repository analysis remains limited to configured local roots or the
   configured HTTPS Git host allowlist. Local snapshots and Git workspaces
   reject symlinks, apply size/count/depth limits, and are read-only copies.
5. RAG document metadata and Chroma search filters include the validated
   owner ID. A user's upload, query, list, lookup, and delete cannot cross into
   another user's document scope.
6. Reports, exports, and artifact downloads are checked against the owner of
   the report. Unknown and cross-owner identifiers return the same not-found
   response.
7. Agent-facing tool use is limited to the read-only Mermaid validator.
   Arguments and MCP structured results are checked by application code; the
   MCP server binds to loopback by default.
8. Approval decisions derive the reviewer from the validated principal rather
   than caller-supplied identity. Requesters can only cancel their own pending
   requests; privileged reviewers can review and execute approved requests.
   Requests expire after a configured timeout. The only approval action remains
   a non-destructive simulation.

## Role policy

| Operation | Roles |
|---|---|
| Architecture design, repository analysis, report export | Administrator, Architect, Developer |
| RAG upload and delete | Administrator, Architect, Developer |
| Report read/download, RAG query/read, approval request read | All five roles |
| Diagram validation | Administrator, Architect, Developer, Analyst |
| Approval decision and simulated execution | Administrator, Architect |

Unknown role claims grant no permissions. Administrative operations are not
exposed by the current API.

## Secrets and audit

Configuration is supplied through environment variables for local deployment.
Azure deployments should source secrets from Key Vault using managed identity;
this repository does not implement that deployment integration. The root
logging handlers redact common credential patterns and the configured model
key. Security events contain event names, pseudonymous actor IDs, resource IDs,
and outcomes; they do not include request bodies, tokens, prompts, or document
contents.

## Storage and deployment limits

Report and artifact ownership metadata, approval records, and artifact
references are process-local. Document metadata and vectors persist locally,
but deployments must protect their storage volumes and backups. Multi-worker
deployment requires shared storage with transactional ownership enforcement.
The application does not currently provide encryption-at-rest, durable audit
retention, request rate limiting, or Azure Key Vault wiring.
