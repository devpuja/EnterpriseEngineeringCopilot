
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import approvals
from app.services.approval_service import ApprovalService


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(
        approvals,
        "approval_service",
        ApprovalService(),
    )

    test_app = FastAPI()
    test_app.include_router(approvals.router)

    return TestClient(test_app)


def create_request(client: TestClient) -> dict[str, Any]:
    response = client.post(
        "/api/v1/approvals",
        json={
            "target": "staging.feature_enabled",
            "proposed_value": "true",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_create_and_list_pending_request(client: TestClient) -> None:
    request = create_request(client)

    assert request["status"] == "pending"

    response = client.get("/api/v1/approvals")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["request_id"] == request["request_id"]


def test_get_unknown_request_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/approvals/unknown-id")

    assert response.status_code == 404


def test_pending_request_cannot_execute(client: TestClient) -> None:
    request = create_request(client)

    response = client.post(
        f"/api/v1/approvals/{request['request_id']}/execute"
    )

    assert response.status_code == 409
    assert "Only approved" in response.json()["detail"]


def test_approved_request_can_execute(client: TestClient) -> None:
    request = create_request(client)
    request_id = request["request_id"]

    decision_response = client.post(
        f"/api/v1/approvals/{request_id}/decision",
        json={
            "approved": True,
            "reviewer": "local-reviewer",
            "reason": "Approved for demonstration.",
        },
    )

    assert decision_response.status_code == 200
    assert decision_response.json()["status"] == "approved"

    execute_response = client.post(
        f"/api/v1/approvals/{request_id}/execute"
    )

    assert execute_response.status_code == 200
    assert execute_response.json()["status"] == "executed"
    assert execute_response.json()["result"].startswith("SIMULATION ONLY:")


def test_rejected_request_cannot_execute(client: TestClient) -> None:
    request = create_request(client)
    request_id = request["request_id"]

    decision_response = client.post(
        f"/api/v1/approvals/{request_id}/decision",
        json={
            "approved": False,
            "reviewer": "local-reviewer",
            "reason": "Rejected for testing.",
        },
    )

    assert decision_response.status_code == 200
    assert decision_response.json()["status"] == "rejected"

    execute_response = client.post(
        f"/api/v1/approvals/{request_id}/execute"
    )

    assert execute_response.status_code == 409


def test_request_cannot_be_decided_twice(client: TestClient) -> None:
    request = create_request(client)
    request_id = request["request_id"]

    payload: dict[str, Any] = {
        "approved": True,
        "reviewer": "local-reviewer",
    }

    first = client.post(
        f"/api/v1/approvals/{request_id}/decision",
        json=payload,
    )
    second = client.post(
        f"/api/v1/approvals/{request_id}/decision",
        json={**payload, "approved": False},
    )

    assert first.status_code == 200
    assert second.status_code == 409


def test_invalid_decision_payload_returns_422(client: TestClient) -> None:
    request = create_request(client)

    response = client.post(
        f"/api/v1/approvals/{request['request_id']}/decision",
        json={"approved": "not-a-boolean", "reviewer": ""},
    )

    assert response.status_code == 422


def test_unknown_fields_are_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/approvals",
        json={
            "target": "staging.feature_enabled",
            "proposed_value": "true",
            "execute_immediately": True,
        },
    )

    assert response.status_code == 422