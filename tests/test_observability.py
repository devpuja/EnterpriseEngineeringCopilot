import asyncio
import json
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.observability.context import bind_context, current_context
from app.observability.logging import StructuredFormatter, configure_logging, redact_metadata
from app.observability.middleware import RequestContextMiddleware


def test_structured_fields_and_nested_redaction():
    record = logging.LogRecord("app.component", logging.INFO, "", 1, "event=test_completed", (), None)
    record.event_fields = {"operation": "test", "prompt": "private document"}
    with bind_context(request_id="req", correlation_id="corr"):
        output = json.loads(StructuredFormatter("json").format(record))
    assert output["request_id"] == "req"
    assert output["event"] == "test_completed"
    assert "prompt" not in output
    assert redact_metadata({"nested": {"client_secret": "private"}}) == {
        "nested": {"client_secret": "[REDACTED]"}
    }
    assert current_context() == {}


def test_exception_diagnostics_do_not_include_content():
    try:
        raise ValueError("private repository source and access_token=secret")
    except ValueError:
        import sys
        record = logging.LogRecord("component", logging.ERROR, "", 1, "event=failed", (), sys.exc_info())
    output = StructuredFormatter("json").format(record)
    assert "private repository" not in output
    assert "exception_frames" in output
    assert json.loads(output)["error_category"] == "ValueError"


@pytest.mark.asyncio
async def test_concurrent_and_thread_context_is_isolated():
    async def worker(identifier):
        with bind_context(request_id=identifier):
            await asyncio.sleep(0)
            return await asyncio.to_thread(current_context)
    result = await asyncio.gather(worker("one"), worker("two"))
    assert [item["request_id"] for item in result] == ["one", "two"]
    assert current_context() == {}


def test_middleware_correlation_and_public_contract():
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/test")
    def endpoint():
        return current_context()

    client = TestClient(app)
    response = client.get("/test", headers={"X-Correlation-ID": "client-123"})
    assert response.json()["correlation_id"] == "client-123"
    assert response.headers["x-request-id"] == response.json()["request_id"]
    invalid = client.get("/test", headers={"X-Correlation-ID": "unsafe space"})
    assert invalid.headers["x-correlation-id"] == invalid.headers["x-request-id"]


def test_log_configuration(monkeypatch):
    monkeypatch.setattr(logging, "basicConfig", lambda **kwargs: captured.update(kwargs))
    captured = {}
    configure_logging("warning", "json")
    assert captured["level"] == "WARNING"
    assert captured["handlers"][0].formatter.output_format == "json"


@pytest.mark.asyncio
async def test_trace_parent_async_thread_and_error(monkeypatch):
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from opentelemetry.trace import StatusCode
    from app.config.settings import settings
    from app.observability import telemetry

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(telemetry.SafeSpanExporter(exporter)))
    monkeypatch.setattr(settings, "telemetry_enabled", True)
    monkeypatch.setattr(telemetry.trace, "get_tracer", lambda *args: provider.get_tracer("test"))
    with telemetry.operation("parent"):
        await asyncio.to_thread(lambda: _child_operation(telemetry))
        with pytest.raises(ValueError):
            with telemetry.operation("failed"):
                raise ValueError("private prompt")
    spans = {span.name: span for span in exporter.get_finished_spans()}
    assert spans["child"].parent.span_id == spans["parent"].context.span_id
    assert spans["failed"].status.status_code == StatusCode.ERROR
    assert "private prompt" not in str(exporter.get_finished_spans())
    provider.shutdown()


def _child_operation(telemetry):
    with telemetry.operation("child"):
        assert current_context()["trace_id"]


def test_disabled_instrumentation_and_exporter_failure(monkeypatch):
    from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
    from app.config.settings import settings
    from app.observability import telemetry

    monkeypatch.setattr(settings, "telemetry_enabled", False)
    with telemetry.operation("disabled"):
        assert "trace_id" not in current_context()

    class BrokenExporter(SpanExporter):
        def export(self, spans):
            raise ConnectionError("secret credentials")

    assert telemetry.SafeSpanExporter(BrokenExporter()).export([]) == SpanExportResult.FAILURE


def test_shutdown_flush_order_idempotence_and_failure_cleanup(monkeypatch):
    from app.observability import telemetry
    calls = []

    class Provider:
        def __init__(self, name, fail=False):
            self.name, self.fail = name, fail

        def force_flush(self, timeout_millis):
            assert timeout_millis == 3000
            calls.append((self.name, "flush"))
            if self.fail:
                raise ConnectionError("synthetic exporter failure")
            return True

        def shutdown(self):
            calls.append((self.name, "shutdown"))

    monkeypatch.setattr(telemetry, "_shutdown_complete", False)
    monkeypatch.setattr(telemetry, "_meter_provider", Provider("metrics", fail=True))
    monkeypatch.setattr(telemetry, "_provider", Provider("traces"))
    telemetry.shutdown_telemetry()
    telemetry.shutdown_telemetry()
    assert calls == [
        ("metrics", "flush"), ("metrics", "shutdown"),
        ("traces", "flush"), ("traces", "shutdown"),
    ]


@pytest.mark.asyncio
async def test_inbound_trace_context_and_http_failure(monkeypatch):
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from opentelemetry.trace import StatusCode
    from app.observability import telemetry
    from app.config.settings import settings
    from starlette.responses import Response
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(settings, "telemetry_enabled", True)
    monkeypatch.setattr(telemetry.trace, "get_tracer", lambda *args: provider.get_tracer("test"))
    async def denied(scope, receive, send):
        await Response(status_code=403)(scope, receive, send)
    async def receive():
        return {"type":"http.request", "body":b"", "more_body":False}
    messages = []
    async def send(message):
        messages.append(message)
    scope = {
        "type":"http", "method":"GET", "path":"/protected",
        "headers":[(b"traceparent", b"00-11111111111111111111111111111111-2222222222222222-01")],
    }
    await RequestContextMiddleware(denied)(scope, receive, send)
    span = exporter.get_finished_spans()[0]
    assert span.context.trace_id == int("1" * 32, 16)
    assert span.parent.span_id == int("2" * 16, 16)
    assert span.status.status_code == StatusCode.ERROR
    assert span.attributes["outcome"] == "failed"
    provider.shutdown()
