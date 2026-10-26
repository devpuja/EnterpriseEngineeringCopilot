
import logging

import jwt
from jwt import PyJWKClient
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config.settings import settings

logger = logging.getLogger(__name__)


class EntraAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)

        self.tenant_id = settings.entra_tenant_id.strip()
        self.client_id = settings.entra_api_client_id.strip()
        self.required_scope = settings.entra_required_scope.strip()

        self.issuer = (
            f"https://login.microsoftonline.com/"
            f"{self.tenant_id}/v2.0"
        )
        self.jwks_client = PyJWKClient(
            f"https://login.microsoftonline.com/"
            f"{self.tenant_id}/discovery/v2.0/keys"
        )

    async def dispatch(self, request: Request, call_next):
        # Only protect Azure-backed RAG routes in this phase.
        if not (
            settings.rag_backend.strip().lower() == "azure"
            and request.url.path.startswith("/api/v1/rag/")
        ):
            return await call_next(request)

        if request.method == "OPTIONS":
            return await call_next(request)

        if not self.tenant_id or not self.client_id or not self.required_scope:
            logger.error(
                "Azure RAG authentication requires ENTRA_TENANT_ID, "
                "ENTRA_API_CLIENT_ID, and a non-empty ENTRA_REQUIRED_SCOPE."
            )
            return JSONResponse(
                status_code=503,
                content={"detail": "API authentication is not configured. Check application settings."},
            )

        auth_header = request.headers.get("Authorization", "")
        scheme, _, token = auth_header.partition(" ")

        if scheme.lower() != "bearer" or not token:
            return JSONResponse(
                status_code=401,
                content={"detail": "Bearer access token required."},
                headers={"WWW-Authenticate": "Bearer"},
            )

        try:
            signing_key = self.jwks_client.get_signing_key_from_jwt(
                token
            ).key

            claims = jwt.decode(
                token,
                signing_key,
                algorithms=["RS256"],
                audience=self.client_id,
                issuer=self.issuer,
                options={
                    "require": [
                        "exp", "iat", "nbf", "iss", "aud", "tid"
                    ]
                },
            )

            # This API registration is configured for one Entra tenant.
            if claims.get("tid", "").lower() != self.tenant_id.lower():
                raise jwt.InvalidTokenError("Unexpected tenant.")

            scopes = set(claims.get("scp", "").split())
            if self.required_scope not in scopes:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Required API scope is missing."},
                )

            # Only validated claims establish the tenant context.
            request.state.tenant_id = claims["tid"]

        except jwt.PyJWTError:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or expired access token."},
                headers={"WWW-Authenticate": "Bearer"},
            )
        except Exception:
            # Includes key-discovery/network failures: fail closed.
            logger.exception("Entra authentication failed")
            return JSONResponse(
                status_code=503,
                content={"detail": "Authentication service unavailable."},
            )

        return await call_next(request)
