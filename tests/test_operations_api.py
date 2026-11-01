from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api import operations
from app.observability.context import bind_context
from app.observability.metrics import OperationalStore
from app.security import Role, UserPrincipal, get_current_principal
from main import app


def test_owner_scoped_summary_and_estimated_subtotals(monkeypatch):
    alice = UserPrincipal("alice", "https://issuer", frozenset({Role.READ_ONLY}))
    bob = UserPrincipal("bob", "https://issuer", frozenset({Role.ADMINISTRATOR}))
    store = OperationalStore()
    monkeypatch.setattr(operations, "operational_store", store)
    with bind_context(owner_id=alice.owner_id):
        store.record("operation", operation="rag.retrieve", duration_ms=10, outcome="success")
        store.record("operation", operation="rag.retrieve", duration_ms=20, outcome="failed")
        store.record("usage", provider="synthetic", model="fixture",
                     usage={"source":"provider_reported","input_tokens":10,"output_tokens":2},
                     cost={"status":"estimated","amount":"0.1","currency":"USD"})
        store.record("usage", provider="synthetic", model="fixture",
                     usage={"source":"unavailable","input_tokens":None,"output_tokens":None},
                     cost={"status":"unavailable"})
    with bind_context(owner_id=bob.owner_id):
        store.record("operation", operation="private_bob_operation", duration_ms=1, outcome="success")
    previous = app.dependency_overrides[get_current_principal]
    try:
        app.dependency_overrides[get_current_principal] = lambda: alice
        response = TestClient(app).get("/api/v1/operations/summary")
        assert response.status_code == 200
        data = response.json()
        assert data["operations"][0]["mean_duration_ms"] == 15
        assert data["operations"][0]["failures"] == 1
        assert Decimal(data["usage"][0]["estimated_cost_subtotals"]["USD"]) == Decimal(".1")
        assert data["usage"][0]["unavailable_cost_calls"] == 1
        assert "private_bob" not in response.text
        assert "owner_id" not in response.text
        app.dependency_overrides[get_current_principal] = lambda: bob
        assert "rag.retrieve" not in TestClient(app).get("/api/v1/operations/summary").text
    finally:
        app.dependency_overrides[get_current_principal] = previous


def test_operational_api_authentication_authorization_and_window():
    previous = app.dependency_overrides.pop(get_current_principal)
    try:
        assert TestClient(app).get("/api/v1/operations/summary").status_code == 401
        app.dependency_overrides[get_current_principal] = lambda: UserPrincipal("alice", "issuer", frozenset())
        assert TestClient(app).get("/api/v1/operations/summary").status_code == 403
        app.dependency_overrides[get_current_principal] = lambda: UserPrincipal("alice", "issuer", frozenset({Role.DEVELOPER}))
        assert TestClient(app).get("/api/v1/operations/summary?minutes=0").status_code == 422
    finally:
        app.dependency_overrides[get_current_principal] = previous
