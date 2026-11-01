import inspect
import logging
from contextlib import contextmanager
from functools import wraps
from time import perf_counter
from typing import Callable, Iterator, ParamSpec, Sequence, TypeVar, cast

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor, ConsoleSpanExporter, SpanExporter, SpanExportResult,
)
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import Status, StatusCode
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.view import View

from app.observability.context import bind_context, current_context
from app.observability.logging import log_event


logger = logging.getLogger(__name__)
P = ParamSpec("P")
R = TypeVar("R")
_provider: TracerProvider | None = None
_meter_provider: MeterProvider | None = None
_SAFE_ATTRIBUTES = frozenset({
    "operation", "outcome", "error.type", "http.request.method",
    "http.response.status_code", "http.route", "gen_ai.operation.name",
    "gen_ai.provider.name", "gen_ai.system", "gen_ai.request.model",
    "gen_ai.response.model", "gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens",
    "gen_ai.usage.cache_read.input_tokens", "gen_ai.agent.name",
    "gen_ai.tool.name", "retry_count",
})


class SafeSpanExporter(SpanExporter):
    """Export only approved metadata, never model messages or tool arguments."""

    def __init__(self, wrapped: SpanExporter) -> None:
        self.wrapped = wrapped

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        safe = [
            ReadableSpan(
                name=span.name.split(" ", 1)[0][:100],
                context=span.context, parent=span.parent, resource=span.resource,
                attributes={
                    key: value for key, value in (span.attributes or {}).items()
                    if key in _SAFE_ATTRIBUTES
                },
                events=[], links=[], kind=span.kind,
                instrumentation_scope=span.instrumentation_scope,
                start_time=span.start_time, end_time=span.end_time,
                status=Status(span.status.status_code),
            )
            for span in spans
        ]
        try:
            result = self.wrapped.export(safe)
        except Exception as exc:
            logger.warning("event=telemetry_export_failed error_type=%s", type(exc).__name__)
            return SpanExportResult.FAILURE
        if result != SpanExportResult.SUCCESS:
            logger.warning("event=telemetry_export_failed")
        return result

    def shutdown(self) -> None:
        try:
            self.wrapped.shutdown()
        except Exception as exc:
            logger.warning("event=telemetry_shutdown_failed error_type=%s", type(exc).__name__)


def configure_telemetry() -> None:
    global _provider, _meter_provider
    from agent_framework.observability import disable_instrumentation, enable_instrumentation
    from app.config.settings import settings

    if not settings.telemetry_enabled:
        disable_instrumentation()
        return
    if _provider is not None:
        return
    _provider = TracerProvider(
        resource=Resource.create({"service.name": "enterprise-engineering-copilot"}),
        sampler=ParentBased(TraceIdRatioBased(settings.telemetry_sample_ratio)),
    )
    exporter: SpanExporter | None = None
    if settings.telemetry_exporter == "console":
        exporter = ConsoleSpanExporter()
    elif settings.telemetry_exporter == "otlp":
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        exporter = OTLPSpanExporter(endpoint=settings.telemetry_otlp_endpoint, timeout=3)
    else:
        exporter = None
    if exporter is not None:
        _provider.add_span_processor(BatchSpanProcessor(
            SafeSpanExporter(exporter), max_queue_size=512,
            max_export_batch_size=64, schedule_delay_millis=1000,
        ))
    trace.set_tracer_provider(_provider)
    from opentelemetry import metrics
    from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader
    readers = []
    if settings.telemetry_exporter == "console":
        readers = [PeriodicExportingMetricReader(ConsoleMetricExporter(), export_interval_millis=60000)]
    elif settings.telemetry_exporter == "otlp":
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        readers = [PeriodicExportingMetricReader(OTLPMetricExporter(
            endpoint=settings.telemetry_otlp_endpoint.removesuffix("/v1/traces") + "/v1/metrics",
            timeout=3,
        ), export_interval_millis=60000)]
    _meter_provider = MeterProvider(
        metric_readers=readers, resource=_provider.resource,
        views=[View(instrument_name="*", attribute_keys={
            "operation", "outcome", "provider", "model", "direction",
            "gen_ai.operation.name", "gen_ai.provider.name", "gen_ai.system",
            "gen_ai.request.model", "gen_ai.response.model", "gen_ai.agent.name",
            "gen_ai.tool.name", "gen_ai.token.type", "error.type",
        })],
    )
    metrics.set_meter_provider(_meter_provider)
    enable_instrumentation(enable_sensitive_data=False, enable_message_events=False, force=True)


@contextmanager
def operation(
    name: str, *, failed: Callable[[], bool] | None = None,
    parent_context: Context | None = None,
) -> Iterator[None]:
    from app.config.settings import settings

    started = perf_counter()
    tracer = trace.get_tracer(__name__)
    outcome = "success"
    error_category = ""
    with tracer.start_as_current_span(
        name, record_exception=False, set_status_on_exception=False,
        attributes={"operation": name}, context=parent_context,
    ) if settings.telemetry_enabled else _disabled_span() as span:
        context = current_context()
        span_context = span.get_span_context() if span is not None else None
        if span_context and span_context.is_valid:
            context.update(trace_id=f"{span_context.trace_id:032x}", span_id=f"{span_context.span_id:016x}")
        context["operation"] = name
        if name.startswith("workflow."):
            context["workflow"] = name
        if name.startswith("agent."):
            context["agent"] = name
        with bind_context(**context):
            try:
                yield
            except Exception as exc:
                outcome = "failed"
                error_category = type(exc).__name__
                if span is not None:
                    span.set_status(Status(StatusCode.ERROR))
                    span.set_attribute("error.type", error_category)
                raise
            finally:
                if failed is not None and failed():
                    outcome = "failed"
                if outcome == "failed" and span is not None:
                    span.set_status(Status(StatusCode.ERROR))
                duration = (perf_counter() - started) * 1000
                if span is not None:
                    span.set_attribute("outcome", outcome)
                log_event(logger, "operation_completed", operation=name,
                          outcome=outcome, duration_ms=round(duration, 3),
                          error_category=error_category)
                from app.observability.metrics import record_operation
                record_operation(name, duration, outcome)


@contextmanager
def _disabled_span() -> Iterator[None]:
    yield None


def observed(
    name: str, *, failed_result: Callable[[object], bool] | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def decorate(function: Callable[P, R]) -> Callable[P, R]:
        if inspect.iscoroutinefunction(function):
            @wraps(function)
            async def asynchronous(*args: P.args, **kwargs: P.kwargs):
                result: object = None
                with operation(name, failed=lambda: failed_result(result) if failed_result else False):
                    result = await function(*args, **kwargs)
                    return result
            return cast(Callable[P, R], asynchronous)
        @wraps(function)
        def synchronous(*args: P.args, **kwargs: P.kwargs) -> R:
            result: object = None
            with operation(name, failed=lambda: failed_result(result) if failed_result else False):
                result = function(*args, **kwargs)
                return cast(R, result)
        return synchronous
    return decorate
