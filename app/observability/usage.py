import logging
from collections.abc import Mapping
from decimal import Decimal
from typing import Awaitable, Callable

from agent_framework import ChatContext, ChatMiddleware
from pydantic import ValidationError
from opentelemetry import metrics

from app.observability.models import CostEstimate, ModelPricing, TokenUsage
from app.observability.metrics import operational_store
from app.observability.telemetry import operation


logger = logging.getLogger(__name__)


def _field(value: object, name: str) -> object:
    return value.get(name) if isinstance(value, Mapping) else getattr(value, name, None)


def extract_usage(value: object) -> TokenUsage:
    raw = _field(value, "usage_details")
    if raw is None:
        raw = _field(value, "usage")
    if raw is None:
        return TokenUsage(source="unavailable")
    def count(*names: str) -> int | None:
        for name in names:
            number = _field(raw, name)
            if isinstance(number, int) and not isinstance(number, bool) and number >= 0:
                return number
        return None
    cached = count("openai.cached_input_tokens", "cache_read_input_token_count")
    if cached is None:
        details = _field(raw, "prompt_tokens_details") or _field(raw, "input_tokens_details")
        number = _field(details, "cached_tokens")
        if isinstance(number, int) and not isinstance(number, bool) and number >= 0:
            cached = number
    try:
        result = TokenUsage(
            input_tokens=count("input_token_count", "prompt_tokens", "input_tokens"),
            output_tokens=count("output_token_count", "completion_tokens", "output_tokens"),
            total_tokens=count("total_token_count", "total_tokens"),
            cached_input_tokens=cached,
        )
    except ValidationError:
        logger.warning("event=usage_invalid")
        return TokenUsage(source="unavailable")
    if all(value is None for value in (
        result.input_tokens, result.output_tokens, result.total_tokens, result.cached_input_tokens
    )):
        result.source = "unavailable"
    return result


def estimate_cost(usage: TokenUsage, pricing: ModelPricing | None) -> CostEstimate:
    if pricing is None or usage.source == "unavailable" or usage.input_tokens is None or usage.output_tokens is None:
        return CostEstimate(status="unavailable")
    cached = usage.cached_input_tokens
    if pricing.cached_input_per_million is not None and cached is None:
        return CostEstimate(status="unavailable")
    if cached and pricing.cached_input_per_million is None:
        return CostEstimate(status="unavailable")
    cached = cached or 0
    amount = (
        Decimal(usage.input_tokens - cached) * pricing.input_per_million
        + Decimal(usage.output_tokens) * pricing.output_per_million
        + Decimal(cached) * (pricing.cached_input_per_million or Decimal(0))
    ) / Decimal(1_000_000)
    return CostEstimate(status="estimated", amount=amount,
                        currency=pricing.currency, pricing_version=pricing.version)


def record_usage(response: object, provider: str, model: str, *, embedding: bool = False) -> None:
    from app.config.settings import settings
    if not settings.usage_enabled:
        return
    usage = extract_usage(response)
    # Embedding calls produce vectors, not generated output tokens.
    if embedding and usage.input_tokens is not None:
        usage.output_tokens = 0
    pricing = next((item for item in settings.model_pricing if item.provider == provider and item.model == model), None)
    cost = estimate_cost(usage, pricing)
    operational_store.record(
        "usage", provider=provider, model=model[:100],
        usage=usage.model_dump(), cost=cost.model_dump(mode="json"),
    )
    for direction, count in (("input", usage.input_tokens), ("output", usage.output_tokens)):
        if count is not None:
            metrics.get_meter(__name__).create_counter("copilot.llm.tokens", unit="{token}").add(
                count, {"provider": provider, "model": model[:100], "direction": direction}
            )


class UsageMiddleware(ChatMiddleware):
    async def process(self, context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
        from app.config.settings import settings
        with operation("llm.call"):
            await call_next()
            if context.stream:
                context.stream_result_hooks.append(
                    lambda result: record_usage(result, "openai", settings.openai_model)
                )
            elif context.result is not None:
                record_usage(context.result, "openai", settings.openai_model)
