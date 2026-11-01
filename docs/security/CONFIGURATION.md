# Security Configuration

## OIDC / Microsoft Entra ID

The application accepts signed RS256 JWT bearer tokens. Configure:

| Variable | Purpose |
|---|---|
| `AUTH_ISSUER` | Exact trusted issuer (`iss`) for the API access tokens |
| `AUTH_AUDIENCE` | Expected API audience (`aud`) |
| `AUTH_JWKS_URL` | HTTPS URL for the issuer's signing keys |
| `AUTH_CLOCK_SKEW_SECONDS` | Permitted clock skew (0–300 seconds; default 30) |

For Microsoft Entra ID, register an API application and define app roles named
`Administrator`, `Architect`, `Developer`, `Analyst`, and `ReadOnly` as needed.
Assign roles to users/service principals in Entra and request an access token
for this API. Set the tenant-specific v2 issuer and JWKS URL published by the
tenant's OpenID Connect discovery document. Set the audience to the API's
application (client) ID GUID for v2 access tokens, without the `api://` prefix.
Set `api.requestedAccessTokenVersion` to `2` on the API registration.
Use the exact issuer and audience
values present in the issued token; do not accept caller-supplied identity
fields.

An unconfigured issuer, audience, or JWKS URL fails closed with HTTP 503 for
bearer requests. Missing or invalid tokens receive HTTP 401, and insufficient
roles receive HTTP 403. There is no development authentication bypass. The
public endpoints are `/` and `/health`; application operations under
`/api/v1` are protected.

## Local development

Copy `.env.example` to `.env`, set the model provider credentials, and configure
a development OIDC application/tenant. `.env` is ignored by Git. Do not put
real credentials in `.env.example`, tests, or documentation. If auth is not
configured, application routes remain unavailable; health checks remain
available. Security tests use ephemeral signing keys and a mocked JWKS client.

### Swagger user sign-in with one Entra registration

This optional local-demo setup uses the existing API registration as both the
API resource and the browser's public client. It replaces the TestClient
client-secret flow with interactive user sign-in using authorization code and
PKCE. No client secret is required or sent to Swagger. Existing PowerShell
bearer-token calls continue to work. Prefer separate API and client registrations
for production and use HTTPS outside localhost.

Configure the existing **API app registration**:

1. Under **App roles**, allow **Users/Groups** (or **Both** to keep application
   callers) for the exact values `Developer`, `Architect`, and `Administrator`.
   Do not change the IDs of existing roles. If Entra requires disabling a role
   before changing its member types, re-enable it afterward.
2. Under **Expose an API**, keep `api://<API_CLIENT_ID>` and add an enabled
   delegated scope named `access_as_user`. Select **Admins only** for consent
   and supply the consent display name and description.
3. Under **Authentication -> Add a platform -> Single-page application**, add
   `http://localhost:8000/docs/oauth2-redirect`. Use the SPA platform, not Web:
   Swagger exchanges the code in the browser. Do not enable implicit grants
   or configure a browser client secret.
4. Under **API permissions -> Add a permission -> APIs my organization uses**,
   locate this same API by its application ID and add its **Delegated**
   `access_as_user` permission. Grant admin consent for the directory.
5. Under **Enterprise applications**, find this API's service principal and
   use **Users and groups -> Add user/group** to assign each test user an app
   role. These are user assignments on the API, not application permissions on
   the old TestClient. Direct user assignments need no premium group-assignment
   license. Use different users for Developer-only and Architect tests.
6. Ensure `api.requestedAccessTokenVersion` remains `2` in the API manifest.

Set these values in the existing `.env`, replacing all placeholders:

```dotenv
AUTH_ISSUER=https://login.microsoftonline.com/<TENANT_ID>/v2.0
AUTH_AUDIENCE=<API_CLIENT_ID>
AUTH_JWKS_URL=https://login.microsoftonline.com/<TENANT_ID>/discovery/v2.0/keys
SWAGGER_OAUTH_CLIENT_ID=<API_CLIENT_ID>
SWAGGER_OAUTH_SCOPE=api://<API_CLIENT_ID>/access_as_user
```

Both Swagger settings must be configured together. When omitted, Swagger keeps
the manual HTTP Bearer dialog. Restart the server after configuration changes:

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Open **http://localhost:8000/docs**, not the 127.0.0.1 URL, so the callback
matches the registered redirect URI. Click **Authorize**, select the
`access_as_user` scope, leave any secret field blank, and sign in with the
assigned directory user. The client ID should already be populated.
Use **Try it out** on `GET /api/v1/approvals` (200) and create a request (201).
A Developer-only user must get 403 on decisions; an Architect can approve a
pending request (200). Requests expire after 15 minutes by default.

Swagger sends an API access token; do not send an ID token. The API retains
signature/issuer/audience/expiry validation and checks roles from that token,
not the user's Entra directory-administrator status. The delegated scope
enables this consent flow; it does not replace endpoint role checks.
Tokens are not deliberately persisted across page reloads.

If sign-in fails, check the SPA platform and exact redirect URI, delegated
permission/admin consent, and user role assignment on the API enterprise
application. After changing roles, log out of Swagger and authorize again.
Users own a different resource scope from the old application caller, so
TestClient-created reports/documents are not transferred to signed-in users.

Only after user sign-in and role tests succeed should you delete the old
TestClient registration. Deletion prevents new client-credential tokens but
does not guarantee immediate invalidation of previously issued tokens.

## Secrets and Azure production

Local environments may use environment variables loaded from `.env`. For Azure
production, use a managed identity to retrieve secrets from Azure Key Vault or
use platform-injected secret references. Do not bake credentials into images,
deployment manifests, or logs. Key Vault and managed-identity integration is
an operational recommendation, not an implemented service in this repository.

Architecture requirements and retrieved RAG passages are sent to the configured
OpenAI model provider. Use only a provider/deployment approved for the data
classification involved, and review its retention, residency, and processing
terms before indexing or analyzing sensitive material.

Configure `ALLOWED_LOCAL_REPOSITORY_ROOTS` to the narrowest necessary paths.
Do not use a broad drive/root directory. Restrict `GITHUB_ALLOWED_HOSTS`,
repository and upload limits, artifact/document storage, and access to local
SQLite/Chroma data. Configure `APP_ENV`, `LOG_LEVEL`, `MCP_TIMEOUT_SECONDS`,
`APPROVAL_TIMEOUT_SECONDS`, and model settings for the deployment.

## Role assignments and owner isolation

Roles are taken only from the verified token's `roles` array. The resource
owner key is a stable pseudonymous hash of validated issuer and subject claims. Reports,
artifacts, approvals, RAG metadata, and vector retrieval use that owner scope.
The API does not support caller-selected tenant or owner IDs.

On upgrade, legacy RAG rows/vectors without an owner key are intentionally not
returned to authenticated users. Re-upload verified source documents under the
intended identity rather than assigning old shared content to an arbitrary
user.

## Operational requirements

Use HTTPS at the API boundary, protect local storage and backups, retain audit
logs according to organizational policy, and avoid multi-worker deployments
until report, artifact, approval, and ownership state is moved to shared
transactional storage.
