from unittest.mock import Mock

import jwt
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

import app.middleware.entra_auth as auth


@pytest.fixture
def auth_client(monkeypatch):
    monkeypatch.setattr(auth.settings, "rag_backend", "azure")
    monkeypatch.setattr(auth.settings, "entra_tenant_id", "test-tenant")
    monkeypatch.setattr(auth.settings, "entra_api_client_id", "test-client")
    monkeypatch.setattr(auth.settings, "entra_required_scope", "access_as_user")
    for name in ("ENTRA_TENANT_ID", "ENTRA_API_CLIENT_ID", "ENTRA_REQUIRED_SCOPE", "RAG_BACKEND"):
        monkeypatch.delenv(name, raising=False)

    app = FastAPI()
    app.add_middleware(auth.EntraAuthMiddleware)

    @app.get("/health")
    def health():
        return {"status": "healthy"}

    @app.post("/api/v1/rag/documents")
    def upload(request: Request):
        return {"tenant_id": getattr(request.state, "tenant_id", None)}

    return TestClient(app)


def test_settings_work_without_process_environment(auth_client):
    assert auth_client.get("/health").status_code == 200
    response = auth_client.post("/api/v1/rag/documents")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("field", ["entra_tenant_id", "entra_api_client_id", "entra_required_scope"])
def test_missing_configuration_fails_closed(auth_client, monkeypatch, caplog, field):
    monkeypatch.setattr(auth.settings, field, "")
    assert auth_client.get("/health").status_code == 200
    response = auth_client.post("/api/v1/rag/documents")
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]
    assert "Azure RAG authentication requires" in caplog.text


def test_memory_mode_does_not_require_entra_configuration(auth_client, monkeypatch):
    monkeypatch.setattr(auth.settings, "rag_backend", "memory")
    monkeypatch.setattr(auth.settings, "entra_tenant_id", "")
    assert auth_client.post("/api/v1/rag/documents").status_code == 200


@pytest.mark.parametrize(
    ("claims", "status"),
    [
        ({"tid": "test-tenant", "scp": "access_as_user"}, 200),
        ({"tid": "other-tenant", "scp": "access_as_user"}, 401),
        ({"tid": "test-tenant", "scp": "other-scope"}, 403),
    ],
)
def test_claim_checks_use_shared_settings(auth_client, monkeypatch, claims, status):
    jwks = Mock()
    jwks.get_signing_key_from_jwt.return_value.key = "test-signing-key"
    monkeypatch.setattr(auth, "PyJWKClient", Mock(return_value=jwks))
    decode = Mock(return_value=claims)
    monkeypatch.setattr(auth.jwt, "decode", decode)

    response = auth_client.post(
        "/api/v1/rag/documents",
        headers={"Authorization": "Bearer test-token", "X-Tenant-ID": "untrusted"},
    )
    assert response.status_code == status
    assert decode.call_args.kwargs["audience"] == "test-client"
    assert decode.call_args.kwargs["issuer"] == "https://login.microsoftonline.com/test-tenant/v2.0"
    assert decode.call_args.kwargs["algorithms"] == ["RS256"]
    if status == 200:
        assert response.json()["tenant_id"] == "test-tenant"


def test_invalid_token_is_rejected(auth_client, monkeypatch):
    jwks = Mock()
    jwks.get_signing_key_from_jwt.side_effect = jwt.InvalidTokenError("Invalid token")
    monkeypatch.setattr(auth, "PyJWKClient", Mock(return_value=jwks))
    response = auth_client.post(
        "/api/v1/rag/documents", headers={"Authorization": "Bearer invalid"}
    )
    assert response.status_code == 401
