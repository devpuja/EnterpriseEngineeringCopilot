"""Authentication, authorization, and payload-free security audit events."""

import asyncio
import hashlib
import logging
import re
import threading
import traceback
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Callable
from urllib.parse import urlparse

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
    OAuth2AuthorizationCodeBearer,
)
from jwt import PyJWKClient, PyJWKClientConnectionError, PyJWKClientError

from app.config.settings import Settings, settings

logger = logging.getLogger(__name__)

_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+"),
    re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9._~+/-]+=*"),
    re.compile(
        r"(?i)((?:api[_-]?key|account[_-]?key|access[_-]?token|"
        r"refresh[_-]?token|client[_-]?secret|shared[_-]?access[_-]?"
        r"signature|password|secret)\s*[:=]\s*)[^\s,;]+"
    ),
    re.compile(r"(?i)(https?://)[^/@\s:]+:[^/@\s]+@"),
    re.compile(r"(\b)sk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"(\b)gh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"(\b)eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
)


class SecretRedactionFilter(logging.Filter):
    """Redact common credential forms and configured secrets from log messages."""

    @staticmethod
    def _redact(message: str) -> str:
        configured_secrets = (settings.openai_api_key, settings.auth_audience)
        for secret in configured_secrets:
            if secret and len(secret) >= 6:
                message = message.replace(secret, "[REDACTED]")
        for pattern in _SECRET_PATTERNS:
            message = pattern.sub(r"\1[REDACTED]", message)
        return message

    def filter(self, record: logging.LogRecord) -> bool:
        message = self._redact(record.getMessage())
        record.msg = message
        record.args = ()
        if record.exc_info:
            record.exc_text = self._redact(
                "".join(traceback.format_exception(*record.exc_info))
            )
            record.exc_info = None
        return True


class Role(StrEnum):
    ADMINISTRATOR = "Administrator"
    ARCHITECT = "Architect"
    DEVELOPER = "Developer"
    ANALYST = "Analyst"
    READ_ONLY = "ReadOnly"


@dataclass(frozen=True)
class UserPrincipal:
    subject: str
    issuer: str
    roles: frozenset[Role]

    @property
    def owner_id(self) -> str:
        value = f"{self.issuer}|{self.subject}".encode("utf-8")
        return hashlib.sha256(value).hexdigest()

    @property
    def audit_id(self) -> str:
        return self.owner_id[:16]


def create_authentication_scheme(
    configuration: Settings,
) -> HTTPBearer | OAuth2AuthorizationCodeBearer:
    if not configuration.swagger_oauth_client_id:
        return HTTPBearer(auto_error=False)
    authority = configuration.auth_issuer.strip().removesuffix("/v2.0")
    return OAuth2AuthorizationCodeBearer(
        authorizationUrl=f"{authority}/oauth2/v2.0/authorize",
        tokenUrl=f"{authority}/oauth2/v2.0/token",
        scopes={configuration.swagger_oauth_scope: "Access the API as the signed-in user"},
        scheme_name="EntraUserSignIn",
        auto_error=False,
    )


_bearer = create_authentication_scheme(settings)
_jwks_clients: dict[str, PyJWKClient] = {}
_jwks_lock = threading.Lock()
_ROLE_CLAIM = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
_MAX_BEARER_TOKEN_LENGTH = 16_384


def _jwks_client(url: str) -> PyJWKClient:
    with _jwks_lock:
        client = _jwks_clients.get(url)
        if client is None:
            client = PyJWKClient(
                url,
                cache_keys=True,
                cache_jwk_set=True,
                timeout=5,
            )
            _jwks_clients[url] = client
        return client


def _authentication_failure(reason: str) -> HTTPException:
    logger.warning("event=authentication_failed reason=%s", reason)
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication credentials are invalid or missing.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _validate_authentication_configuration() -> tuple[str, str, str]:
    issuer = settings.auth_issuer.strip()
    audience = settings.auth_audience.strip()
    jwks_url = settings.auth_jwks_url.strip()
    parsed = urlparse(jwks_url)
    if (
        not issuer
        or not audience
        or parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
    ):
        logger.error("event=authentication_configuration_invalid")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured for this service.",
        )
    return issuer, audience, jwks_url


def _decode_token(token: str) -> UserPrincipal:
    issuer, audience, jwks_url = _validate_authentication_configuration()
    signing_key = _jwks_client(jwks_url).get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=audience,
        issuer=issuer,
        leeway=settings.auth_clock_skew_seconds,
        options={"require": ["exp", "iat", "iss", "aud", "sub"]},
    )
    subject = claims.get("sub")
    token_issuer = claims.get("iss")
    raw_roles = claims.get("roles", [])
    if (
        not isinstance(subject, str)
        or not subject.strip()
        or len(subject) > 256
        or token_issuer != issuer
        or not isinstance(raw_roles, list)
        or any(not isinstance(role, str) or not _ROLE_CLAIM.fullmatch(role) for role in raw_roles)
    ):
        raise jwt.InvalidTokenError("Required identity claims are invalid.")
    known_roles = {role.value: role for role in Role}
    roles = frozenset(known_roles[role] for role in raw_roles if role in known_roles)
    return UserPrincipal(subject=subject, issuer=issuer, roles=roles)


async def get_current_principal(
    credentials: Annotated[
        HTTPAuthorizationCredentials | str | None,
        Depends(_bearer),
    ],
) -> UserPrincipal:
    if credentials is None:
        raise _authentication_failure("missing_bearer_token")
    if isinstance(credentials, str):
        token = credentials
    else:
        if credentials.scheme.lower() != "bearer":
            raise _authentication_failure("missing_bearer_token")
        token = credentials.credentials
    if not token:
        raise _authentication_failure("missing_bearer_token")
    if len(token) > _MAX_BEARER_TOKEN_LENGTH:
        raise _authentication_failure("token_too_large")

    try:
        principal = await asyncio.to_thread(_decode_token, token)
    except PyJWKClientConnectionError as exc:
        logger.error(
            "event=authentication_key_service_unavailable error_type=%s",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication could not be completed.",
        ) from exc
    except (jwt.PyJWTError, PyJWKClientError, ValueError, TypeError) as exc:
        logger.warning(
            "event=authentication_failed reason=invalid_token error_type=%s",
            type(exc).__name__,
        )
        raise _authentication_failure("invalid_token") from exc

    audit_security_event("authentication_succeeded", principal=principal)
    return principal


def require_roles(*allowed_roles: Role) -> Callable[..., UserPrincipal]:
    async def enforce_role(
        principal: Annotated[UserPrincipal, Depends(get_current_principal)],
    ) -> UserPrincipal:
        if not principal.roles.intersection(allowed_roles):
            audit_security_event(
                "authorization_denied",
                principal=principal,
                outcome="denied",
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="The authenticated identity is not authorized for this operation.",
            )
        return principal

    return enforce_role


def audit_security_event(
    event: str,
    *,
    principal: UserPrincipal | None = None,
    resource_id: str | None = None,
    outcome: str = "success",
) -> None:
    fields = [f"event={event}", f"outcome={outcome}"]
    if principal is not None:
        fields.append(f"actor={principal.audit_id}")
    if resource_id is not None:
        fields.append(f"resource_id={resource_id}")
    logger.info(" ".join(fields))
