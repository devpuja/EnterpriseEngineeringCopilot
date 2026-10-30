import pytest

from app.repository.adapters.local_repository import LocalRepositoryAdapter
from app.repository.analysis.repository_analyzer import RepositoryAnalyzer
from app.repository.workspace_manager import WorkspaceManager


async def analyze_source(tmp_path, files):
    source = tmp_path / "source"
    source.mkdir()
    for relative, content in files.items():
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    manager = WorkspaceManager(tmp_path / "workspaces", maximum_storage_bytes=10 * 1024 * 1024)
    snapshot = await LocalRepositoryAdapter(
        workspace_manager=manager,
        allowed_roots=[str(tmp_path)],
    ).retrieve(str(source))
    return RepositoryAnalyzer(manager).analyze(snapshot), snapshot


@pytest.mark.asyncio
async def test_dotnet_web_api_analysis(tmp_path):
    result, snapshot = await analyze_source(tmp_path, {
        "Web.csproj": '<Project Sdk="Microsoft.NET.Sdk.Web"><ItemGroup><PackageReference Include="Microsoft.EntityFrameworkCore" Version="8.0.0"/></ItemGroup></Project>',
        "Program.cs": 'var builder = WebApplication.CreateBuilder(args); builder.Services.AddDbContext<AppDb>(); var app = builder.Build(); app.MapGet("/health", () => "ok"); app.Run();',
        "Controllers/OrdersController.cs": '[ApiController]\\n[Route("api/orders")]\\npublic class OrdersController : ControllerBase {\\n[HttpGet("{id}")] public object Get(int id) => new { id };\\n}',
    })
    names = {item.name for item in result.technology_stack}
    assert "ASP.NET Core" in names
    assert "Entity Framework Core" in names
    assert sum(item.name == "ASP.NET Core" for item in result.technology_stack) == 1
    assert sum(item.name == "Entity Framework Core" for item in result.technology_stack) == 1
    assert any(endpoint.exposure == "exposed" for endpoint in result.api_endpoints)
    assert any("DbContext" in finding.detail for finding in result.database_findings) or result.database_findings
    assert all("source_reference" not in evidence.relative_path for evidence in result.evidence)


@pytest.mark.asyncio
async def test_python_fastapi_and_mixed_detection(tmp_path):
    result, snapshot = await analyze_source(tmp_path, {
        "pyproject.toml": "[project]\ndependencies=['fastapi==0.115.0','sqlalchemy==2.0.0']",
        "app/main.py": "from fastapi import FastAPI\\nfrom .database import engine\\napp = FastAPI()\\n@app.get('/items/{item_id}')\\ndef item(item_id: int): return {'item_id': item_id}",
        "app/database.py": "from sqlalchemy import create_engine\\nengine = create_engine('sqlite:///app.db')",
        "package.json": '{"dependencies":{"react":"18.3.0","axios":"1.7.0"}}',
        "src/App.tsx": 'import React from "react"; import axios from "axios"; export function App(){ return axios.get("/api/users"); }',
    })
    names = {item.name for item in result.technology_stack}
    assert {"FastAPI", "SQLAlchemy", "React", "Python"} <= names
    assert sum(item.name == "FastAPI" for item in result.technology_stack) == 1
    assert sum(item.name == "SQLAlchemy" for item in result.technology_stack) == 1
    assert sum(item.name == "React" for item in result.technology_stack) == 1
    assert sum(item.name == "Python" for item in result.technology_stack) == 1
    assert any(endpoint.exposure == "exposed" and endpoint.route == "/items/{item_id}" for endpoint in result.api_endpoints)
    assert any(endpoint.exposure == "consumed" for endpoint in result.api_endpoints)
    assert any(finding.technology == "SQLAlchemy" for finding in result.database_findings)


@pytest.mark.asyncio
async def test_database_secrets_are_not_copied(tmp_path):
    result, snapshot = await analyze_source(tmp_path, {
        "appsettings.json": '{"ConnectionStrings":{"Database":"Server=localhost;Password=super-secret"}}',
        "app.py": "DATABASE_URL='postgresql://user:password@localhost/db'",
    })
    serialized = result.model_dump_json()
    assert "super-secret" not in serialized
    assert "password@" not in serialized
    assert any(finding.detail.startswith("Configuration key:") for finding in result.database_findings)


@pytest.mark.asyncio
async def test_inconclusive_repository_is_explicit(tmp_path):
    result, snapshot = await analyze_source(tmp_path, {
        "README.md": "# Small sample",
        "notes.txt": "No implementation files.",
    })
    assert result.architectural_patterns
    assert result.architectural_patterns[0].name == "Not determined"
    assert result.project_structure.summary


@pytest.mark.asyncio
async def test_dotnet_controller_routes_are_combined(tmp_path):
    result, _ = await analyze_source(tmp_path, {
        "Controllers/OrdersController.cs": (
            '[Route("api/orders")]\n'
            "public class OrdersController : ControllerBase {\n"
            '[HttpGet("{id}")]\n'
            "public object Get(int id) => new { id };\n"
            "}"
        ),
    })
    assert any(
        endpoint.framework == "ASP.NET Core"
        and endpoint.route == "/api/orders/{id}"
        for endpoint in result.api_endpoints
    )


@pytest.mark.asyncio
async def test_dotnet_minimal_api_methods_are_detected(tmp_path):
    result, _ = await analyze_source(tmp_path, {
        "Program.cs": (
            'var app = WebApplication.Create();\n'
            'app.MapGet("/health", () => "ok");\n'
            'app.MapPost("/orders", () => "ok");\n'
            'app.MapPut("/orders/{id}", () => "ok");\n'
            'app.MapDelete("/orders/{id}", () => "ok");\n'
            'app.MapPatch("/orders/{id}", () => "ok");\n'
            'app.MapGet(GetRouteName(), () => "dynamic");\n'
        ),
    })
    endpoints = {
        (endpoint.method, endpoint.route)
        for endpoint in result.api_endpoints
        if endpoint.framework == "ASP.NET Core"
    }
    assert endpoints >= {
        ("GET", "/health"),
        ("POST", "/orders"),
        ("PUT", "/orders/{id}"),
        ("DELETE", "/orders/{id}"),
        ("PATCH", "/orders/{id}"),
    }
    for endpoint in result.api_endpoints:
        if endpoint.framework == "ASP.NET Core":
            assert endpoint.relative_path == "Program.cs"
            assert endpoint.evidence_references
            assert any(
                evidence.evidence_id in endpoint.evidence_references
                for evidence in result.evidence
            )


@pytest.mark.asyncio
async def test_python_relative_and_absolute_imports_resolve(tmp_path):
    result, _ = await analyze_source(tmp_path, {
        "app/main.py": "from .database import engine",
        "app/database.py": "engine = object()",
        "app/controllers/api.py": "from ..services.user_service import UserService",
        "app/services/user_service.py": "class UserService: pass",
        "app/unresolved.py": "from .missing_module import Missing",
        "consumer.py": "import app.services.user_service",
    })
    resolved = {(item.source, item.target) for item in result.dependencies if item.resolved}
    assert ("app/main.py", "app/database.py") in resolved
    assert ("app/controllers/api.py", "app/services/user_service.py") in resolved
    assert ("consumer.py", "app/services/user_service.py") in resolved
    assert not any(item.source == "app/unresolved.py" for item in result.dependencies)


@pytest.mark.asyncio
async def test_misleading_pattern_directory_names_are_inconclusive(tmp_path):
    result, _ = await analyze_source(tmp_path, {
        "domain/README.md": "Domain folder placeholder.",
        "application/README.md": "Application folder placeholder.",
        "infrastructure/README.md": "Infrastructure folder placeholder.",
        "presentation/README.md": "Presentation folder placeholder.",
        "controllers/empty.txt": "placeholder",
        "models/empty.txt": "placeholder",
        "views/empty.txt": "placeholder",
        "repositories/empty.txt": "placeholder",
    })
    pattern_names = {item.name for item in result.architectural_patterns}
    assert "Not determined" in pattern_names
    assert "Layered Architecture" not in pattern_names
    assert "MVC" not in pattern_names
    assert "Repository Pattern" not in pattern_names
