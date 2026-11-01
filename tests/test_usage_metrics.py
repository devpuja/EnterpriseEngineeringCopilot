from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.observability.context import bind_context
from app.observability.models import ModelPricing, TokenUsage
from app.observability.metrics import OperationalStore
from app.observability.usage import UsageMiddleware, estimate_cost, extract_usage


def test_provider_variants_and_missing_usage():
    maf = extract_usage(SimpleNamespace(usage_details={
        "input_token_count": 100, "output_token_count": 20,
        "total_token_count": 120, "openai.cached_input_tokens": 40,
    }))
    sdk = extract_usage({"usage": {
        "prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120,
        "prompt_tokens_details": {"cached_tokens": 40},
    }})
    assert maf == sdk
    assert extract_usage({}).source == "unavailable"
    assert extract_usage({"usage": {"prompt_tokens": True}}).input_tokens is None
    assert extract_usage({"usage": {"prompt_tokens": 1, "prompt_tokens_details": {"cached_tokens": 2}}}).source == "unavailable"


def test_exact_cost_and_unavailable_prices():
    # Synthetic arithmetic fixture, not published provider pricing.
    pricing = ModelPricing(provider="synthetic", model="fixture",
        input_per_million="2", output_per_million="4", cached_input_per_million="1",
        currency="USD", version="synthetic-test")
    usage = TokenUsage(input_tokens=100, output_tokens=20, cached_input_tokens=40)
    assert estimate_cost(usage, pricing).amount == Decimal("0.00024")
    assert estimate_cost(usage, None).status == "unavailable"
    assert estimate_cost(TokenUsage(input_tokens=100, output_tokens=20), pricing).status == "unavailable"
    assert estimate_cost(TokenUsage(source="unavailable"), pricing).status == "unavailable"


def test_bounded_owner_and_window_aggregation():
    store = OperationalStore(2)
    with bind_context(owner_id="alice"):
        store.record("operation", operation="one", duration_ms=1, outcome="success")
        store.record("operation", operation="two", duration_ms=1, outcome="success")
    with bind_context(owner_id="bob"):
        store.record("operation", operation="three", duration_ms=1, outcome="success")
    assert [row.operation for row in store.records("alice")] == ["two"]
    assert [row.operation for row in store.records("bob")] == ["three"]
    assert store.records("unknown") == []


@pytest.mark.asyncio
async def test_client_middleware_records_once_and_preserves_result(monkeypatch):
    from agent_framework import ChatContext, ChatResponse
    from app.observability import usage
    records = []
    monkeypatch.setattr(usage, "record_usage", lambda *args: records.append(args))
    response = ChatResponse(usage_details={"input_token_count": 2, "output_token_count": 3})
    context = ChatContext(client=SimpleNamespace(), messages=[], options={})
    async def next_call():
        context.result = response
    await UsageMiddleware().process(context, next_call)
    assert context.result is response
    assert len(records) == 1


def test_durations_failures_and_retries(monkeypatch):
    from app.observability import metrics, telemetry
    store = OperationalStore()
    monkeypatch.setattr(metrics, "operational_store", store)
    with bind_context(owner_id="alice"):
        with telemetry.operation("test.success"):
            pass
        with pytest.raises(TimeoutError):
            with telemetry.operation("test.failure"):
                raise TimeoutError()
        metrics.record_retry("test.failure")
    rows = store.records("alice")
    assert rows[0].duration_ms >= 0
    assert rows[1].outcome == "failed"
    assert rows[2].kind == "retry"
