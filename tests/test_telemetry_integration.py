import os
from pathlib import Path
import subprocess
import sys


def test_enabled_native_maf_and_repository_trace_in_isolated_process(tmp_path):
    script = r'''
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode
from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient
from openai import AsyncOpenAI
import httpx
from app.config.settings import settings
from app.observability.telemetry import _provider, SafeSpanExporter, operation
from app.observability.context import bind_context
from app.observability.metrics import operational_store
from app.observability.models import UsageObservation
from app.observability.usage import UsageMiddleware
from main import app
from app.api import repository_reports
from app.services.repository_report_service import RepositoryReportService
from app.repository.adapters.local_repository import LocalRepositoryAdapter
from app.repository.workspace_manager import WorkspaceManager
from app import security

# main startup installs the provider; never sends data to an external backend.
from app.observability.telemetry import _provider
exporter = InMemorySpanExporter()
_provider.add_span_processor(SimpleSpanProcessor(SafeSpanExporter(exporter)))
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
settings.auth_issuer = "https://issuer.example/tenant"
settings.auth_audience = "fixture-api"
settings.auth_jwks_url = "https://issuer.example/keys"
security._jwks_clients.clear()
security._jwks_client = lambda url: SimpleNamespace(
    get_signing_key_from_jwt=lambda token: SimpleNamespace(key=key.public_key())
)
now = datetime.now(timezone.utc)
token = jwt.encode({"iss":settings.auth_issuer,"aud":settings.auth_audience,
    "sub":"fixture-user","iat":now,"exp":now+timedelta(minutes=5),"roles":["Developer"]},
    key,algorithm="RS256")
with TemporaryDirectory() as temp:
    root = Path(temp)
    repo = root / "synthetic"
    repo.mkdir()
    (repo / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n")
    workspace = WorkspaceManager(root / "workspaces")
    repository_reports.repository_report_service = RepositoryReportService(
        workspace_manager=workspace,
        local_adapter=LocalRepositoryAdapter(workspace,allowed_roots=[str(root)]),
        output_directory=root / "artifacts",
    )
    client = TestClient(app)
    headers = {"Authorization":f"Bearer {token}","X-Correlation-ID":"fixture"}
    response = client.post("/api/v1/repository-reports/analyses",headers=headers,
        json={"source_type":"local","source_reference":str(repo)})
    assert response.status_code == 201, response.text
    report_id = response.json()["report"]["report_id"]
    exported = client.post(f"/api/v1/repository-reports/{report_id}/exports",
        headers=headers,json={"format":"markdown"})
    assert exported.status_code == 201, exported.text
    downloaded = client.get(exported.json()["artifacts"][0]["download_url"], headers=headers)
    assert downloaded.status_code == 200
    summary = client.get("/api/v1/operations/summary",headers=headers)
    assert summary.status_code == 200
    assert any(row["operation"] == "repository.analyze" for row in summary.json()["operations"])
    spans = list(exporter.get_finished_spans())
    workflow = next(span for span in spans if span.name == "workflow.repository_report")
    for name in ["repository.retrieve_local","repository.analyze","repository.visualize",
        "repository.synthesize","repository.review","report.generate"]:
        child = next(span for span in spans if span.name == name)
        assert child.context.trace_id == workflow.context.trace_id, name
        assert child.parent.span_id == workflow.context.span_id, name
    names = {span.name for span in spans}
    assert {"export.markdown","artifact.persist","artifact.resolve"} <= names
    assert str(repo) not in str(spans)

async def check_maf():
    def respond(request):
        return httpx.Response(200, json={
            "id":"resp_fixture","object":"response","created_at":1,"status":"completed",
            "model":"synthetic-model","parallel_tool_calls":False,
            "output":[{"id":"msg_fixture","type":"message","status":"completed",
                "role":"assistant","content":[{"type":"output_text",
                    "text":"PRIVATE RESPONSE","annotations":[]}]}],
            "usage":{"input_tokens":10,"output_tokens":2,"total_tokens":12,
                "input_tokens_details":{"cached_tokens":0},
                "output_tokens_details":{"reasoning_tokens":0}},
            "tool_choice":"auto","tools":[],"temperature":1,"top_p":1,
            "error":None,"incomplete_details":None,"instructions":None,
        })
    sdk = AsyncOpenAI(api_key="synthetic-key",max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)))
    settings.openai_model = "synthetic-model"
    chat = OpenAIChatClient(model="synthetic-model",async_client=sdk,middleware=[UsageMiddleware()])
    with bind_context(owner_id="fixture-owner"):
        with operation("agent.fixture"):
            await Agent(client=chat,name="FixtureAgent").run("PRIVATE PROMPT")
    usage = [row for row in operational_store.records("fixture-owner") if isinstance(row,UsageObservation)]
    assert len(usage) == 1
    assert usage[0].usage.input_tokens == 10
    assert usage[0].usage.output_tokens == 2
    spans = exporter.get_finished_spans()
    assert "PRIVATE PROMPT" not in str(spans)
    assert "PRIVATE RESPONSE" not in str(spans)
    assert any(span.attributes.get("gen_ai.usage.input_tokens") == 10 for span in spans)
    await sdk.close()

asyncio.run(check_maf())

# A bounded loopback-only MCP integration check; never contact an external server.
import socket
import threading
import time
import uvicorn
from app.mcp_server import mcp_server
from app.observability.middleware import RequestContextMiddleware
from app.services.mcp_client_service import validate_architecture_diagram
sock = socket.socket()
sock.bind(("127.0.0.1",0))
sock.listen(128)
settings.mcp_server_url = f"http://127.0.0.1:{sock.getsockname()[1]}/mcp"
mcp_app = mcp_server.streamable_http_app(stateless_http=True)
mcp_app.add_middleware(RequestContextMiddleware)
server = uvicorn.Server(uvicorn.Config(mcp_app,log_level="warning"))
thread = threading.Thread(target=lambda: server.run(sockets=[sock]),daemon=True)
thread.start()
try:
    deadline = time.monotonic() + 5
    while not server.started and time.monotonic() < deadline:
        time.sleep(.01)
    assert server.started
    async def check_mcp():
        with operation("workflow.mcp_fixture"):
            answer = await validate_architecture_diagram("flowchart LR\nA[API] --> B[Worker]")
            assert json.loads(answer)["valid"]
    asyncio.run(check_mcp())
    spans = exporter.get_finished_spans()
    mcp_root = next(span for span in spans if span.name == "workflow.mcp_fixture")
    tool_span = next(span for span in spans if span.name == "tool.validate_diagram")
    assert tool_span.context.trace_id == mcp_root.context.trace_id
    assert any(span.name == "mcp.validate_diagram" for span in spans)
finally:
    server.should_exit = True
    thread.join(timeout=5)
    sock.close()
    assert not thread.is_alive()
from app.observability.telemetry import shutdown_telemetry
shutdown_telemetry()
shutdown_telemetry()
print("Enabled HTTP/JWT/repository/export/download/native-MAF/MCP/usage/privacy checks passed.")
'''
    environment = {
        **os.environ, "TELEMETRY_ENABLED":"true", "TELEMETRY_EXPORTER":"none",
        "SWAGGER_OAUTH_CLIENT_ID":"", "SWAGGER_OAUTH_SCOPE":"",
        "USAGE_ENABLED":"true", "MODEL_PRICING":"[]",
        "CHROMA_PERSIST_DIRECTORY":str(tmp_path / "chroma"),
        "RAG_METADATA_DATABASE":str(tmp_path / "metadata.db"),
        "REPOSITORY_WORKSPACE_ROOT":str(tmp_path / "workspaces"),
        "LOG_LEVEL":"WARNING",
    }
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[1],
        env=environment, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "checks passed" in result.stdout


def test_console_exporters_stop_before_stream_teardown(tmp_path):
    script = r'''
import threading
from main import app
from fastapi.testclient import TestClient
from app.observability import telemetry
workers = [
    thread for thread in threading.enumerate()
    if thread.name.startswith(("Otel", "OpenTelemetry"))
]
assert workers, "Expected SDK exporter workers."
with TestClient(app) as client:
    assert client.get("/health").status_code == 200
telemetry.shutdown_telemetry()
assert telemetry._shutdown_complete
assert all(not worker.is_alive() for worker in workers)
print("Console lifecycle clean.")
'''
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[1],
        env={
            **os.environ, "TELEMETRY_ENABLED": "true", "TELEMETRY_EXPORTER": "console",
            "CHROMA_PERSIST_DIRECTORY": str(tmp_path / "chroma"),
            "RAG_METADATA_DATABASE": str(tmp_path / "metadata.db"),
        },
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Console lifecycle clean." in result.stdout
    assert "copilot.operation" in result.stdout
    assert "Logging error" not in result.stderr
    assert "closed file" not in result.stderr
