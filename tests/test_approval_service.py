
import pytest

from app.services.approval_service import (
    ApprovalService,
    ApprovalStateError,
    ApprovalStatus,
)


@pytest.fixture
def service() -> ApprovalService:
    return ApprovalService()


def test_new_request_starts_pending(service: ApprovalService) -> None:
    request = service.create_request(
        target="staging.feature_enabled",
        proposed_value="true",
    )

    assert request.status == ApprovalStatus.PENDING
    assert request.tool_name == "simulate_configuration_change"


def test_pending_request_cannot_execute(service: ApprovalService) -> None:
    request = service.create_request(
        target="staging.feature_enabled",
        proposed_value="true",
    )

    with pytest.raises(ApprovalStateError, match="Only approved"):
        service.execute_simulated_action(request.request_id)


def test_rejected_request_cannot_execute(service: ApprovalService) -> None:
    request = service.create_request(
        target="staging.feature_enabled",
        proposed_value="true",
    )
    service.decide(
        request.request_id,
        approved=False,
        reviewer="reviewer-1",
    )

    with pytest.raises(ApprovalStateError, match="Only approved"):
        service.execute_simulated_action(request.request_id)


def test_approved_request_executes_once(service: ApprovalService) -> None:
    request = service.create_request(
        target="staging.feature_enabled",
        proposed_value="true",
    )
    service.decide(
        request.request_id,
        approved=True,
        reviewer="reviewer-1",
    )

    executed = service.execute_simulated_action(request.request_id)

    assert executed.status == ApprovalStatus.EXECUTED
    assert executed.result is not None
    assert executed.result.startswith("SIMULATION ONLY:")

    with pytest.raises(ApprovalStateError, match="Only approved"):
        service.execute_simulated_action(request.request_id)


def test_request_cannot_receive_two_decisions(
    service: ApprovalService,
) -> None:
    request = service.create_request(
        target="staging.feature_enabled",
        proposed_value="true",
    )
    service.decide(
        request.request_id,
        approved=True,
        reviewer="reviewer-1",
    )

    with pytest.raises(ApprovalStateError, match="Only pending"):
        service.decide(
            request.request_id,
            approved=False,
            reviewer="reviewer-2",
        )


def test_execution_uses_original_approved_arguments(service: ApprovalService) -> None:
    request = service.create_request(
        target="staging.feature_enabled",
        proposed_value="true",
    )
    service.decide(
        request.request_id,
        approved=True,
        reviewer="reviewer-1",
    )

    executed = service.execute_simulated_action(request.request_id)

    assert executed.arguments.target == "staging.feature_enabled"
    assert executed.arguments.proposed_value == "true"
    assert executed.result is not None
    assert "'staging.feature_enabled' to 'true'" in executed.result