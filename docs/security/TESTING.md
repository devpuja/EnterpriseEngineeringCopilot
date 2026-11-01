# Security Testing

Run focused security tests:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_security.py tests\test_approvals_api.py tests\test_repository_reports_api.py
```

Run authentication cases with generated ephemeral RSA keys and a mocked JWKS
endpoint. Tests cover missing/malformed credentials, valid tokens, expiration,
issuer/audience and claim validation, role denial, and unconfigured auth.

The security suite also tests secret redaction, owner-scoped document metadata
and vector search, owner-separated document identifiers, approval ownership
and expiry, and malformed MCP output. Repository report API tests verify that
another identity cannot read, export, or download a report's artifacts.
Repository and artifact path traversal/symlink coverage remains in the existing
`tests\repository` and report API suites. The RAG adversarial test verifies
that hostile document text is presented to the model as untrusted data without
granting it any application tool capability.

Run the complete regression suite and static checks:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q app main.py
git diff --check
```

For deployment validation, request a token from the configured identity
provider for the API audience, verify that `/health` remains reachable, then
verify that API requests fail without a token and that role-restricted calls
return 403 for identities without the required app role. Review structured
`event=...` logs for audit events; they intentionally omit tokens, prompts,
request bodies, and document text.
