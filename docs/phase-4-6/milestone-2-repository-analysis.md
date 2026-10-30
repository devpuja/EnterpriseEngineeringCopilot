# Phase 4.6 Milestone 2: Repository Investigation and Architecture Analysis

## Objective

Milestone 2 performs deterministic, static analysis of an existing Milestone 1 `RepositorySnapshot`. It produces evidence-based technology, structure, dependency, API, persistence, integration, and architectural-pattern findings without executing repository code.

## Architecture

- `RepositoryAnalyzer` orchestrates all stages.
- `TechnologyDetector` and technology-specific analyzers identify supported .NET/C#, Python, Angular, and React evidence.
- `ProjectStructureAnalyzer` groups projects, source/test/configuration areas, entry points, and shared directories.
- `DependencyAnalyzer`, `APIAnalyzer`, `DatabaseAnalyzer`, and `IntegrationAnalyzer` identify repository relationships.
- `ArchitecturePatternDetector` reports only patterns supported by static evidence.
- `EvidenceCollector` provides reusable evidence references with repository-relative paths and optional accurate line information.
- `SnapshotContentReader` reads only files inside the snapshot workspace and never exposes absolute workspace paths.

## Supported analysis

The analyzer supports `.NET/C#`, Python, Angular, and React evidence:

- project and solution manifests;
- ASP.NET Core, FastAPI, Flask, Django, Angular, React, and persistence packages;
- static application entry points;
- C# project references and Python internal imports;
- declared exposed routes and client-side consumed API calls;
- Entity Framework Core, SQLAlchemy, Django ORM, repositories, and redacted database configuration keys;
- HTTP, messaging, cloud, authentication, and storage integration indicators.

## Evidence and confidence

Every finding uses a typed confidence level: `high`, `medium`, or `low`. Evidence references include a relative file path, category, explanation, optional symbol, and optional line range. Findings are deduplicated where possible.

## Security restrictions

Milestone 2 never executes repository files, build scripts, package managers, or shell commands. It reads only non-binary discovered files within the repository workspace, rejects path escape and symlink access, caps content reads at repository file limits, and never logs or emits secret values. Database configuration results report keys and technologies, not connection-string values.

## Example result

```json
{
  "repository_name": "sample-api",
  "source_type": "local",
  "technology_stack": [
    {
      "name": "ASP.NET Core",
      "category": "framework",
      "confidence": "high",
      "evidence_references": ["E0001"]
    }
  ],
  "architectural_patterns": [
    {
      "name": "Dependency Injection",
      "confidence": "high",
      "limitations": "Dependency lifetime and runtime composition are not fully demonstrated statically."
    }
  ],
  "analysis_warnings": [],
  "limitations": ["Static analysis only; runtime behavior and deployment topology were not observed."]
}
```

## Known limitations

- Static evidence cannot prove runtime deployment topology.
- Folder names and project names are not treated as sufficient proof of Clean Architecture, microservices, or other patterns.
- Dynamic framework generation, metaprogramming, and generated configuration may not be detected.
- Client-side HTTP calls are classified as consumed APIs unless repository implementation evidence is present.
- Malformed files are handled with partial results and warnings.

## Running tests

```powershell
.venv\Scripts\python.exe -m pytest tests/repository/analysis -q
.venv\Scripts\python.exe -m pytest tests/repository -q
.venv\Scripts\python.exe -m pytest -q
```
