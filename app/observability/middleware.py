import logging
import re
from time import perf_counter
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.observability.context import bind_context
from app.observability.logging import log_event
from app.observability.telemetry import operation
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator


logger = logging.getLogger(__name__)
_CORRELATION = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = uuid4().hex
        supplied = dict(scope.get("headers", [])).get(b"x-correlation-id", b"")
        correlation = supplied.decode("ascii", errors="replace")
        if not _CORRELATION.fullmatch(correlation):
            correlation = request_id
        started = perf_counter()
        carrier = {
            key.decode("ascii"): value.decode("ascii", errors="replace")
            for key, value in scope.get("headers", [])
            if key in {b"traceparent", b"tracestate"} and len(value) <= 512
        }
        parent_context = TraceContextTextMapPropagator().extract(carrier)
        status_code = 500
        trace_id = ""

        async def respond(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                message["headers"] = [
                    (key, value) for key, value in message.get("headers", [])
                    if key.lower() not in {b"x-request-id", b"x-correlation-id"}
                ] + [
                    (b"x-request-id", request_id.encode("ascii")),
                    (b"x-correlation-id", correlation.encode("ascii")),
                ]
            await send(message)

        with bind_context(request_id=request_id, correlation_id=correlation):
            try:
                with operation("http.request", failed=lambda: status_code >= 400,
                               parent_context=parent_context):
                    await self.app(scope, receive, respond)
                    from opentelemetry import trace
                    span = trace.get_current_span()
                    span_context = span.get_span_context()
                    if span_context.is_valid:
                        trace_id = f"{span_context.trace_id:032x}"
                    span.set_attribute("http.route", getattr(scope.get("route"), "path", "unmatched"))
                    span.set_attribute("http.response.status_code", status_code)
                    span.set_attribute("http.request.method", scope.get("method", ""))
            except Exception as exc:
                logger.error(
                    "event=request_failed",
                    extra={"event_fields": {"error_category": type(exc).__name__}},
                    exc_info=True,
                )
                raise
            finally:
                route = scope.get("route")
                log_event(
                    logger, "request_completed",
                    operation=getattr(route, "path", "unmatched"),
                    duration_ms=round((perf_counter() - started) * 1000, 3),
                    status_code=status_code,
                    outcome="failed" if status_code >= 400 else "success",
                    trace_id=trace_id,
                )
