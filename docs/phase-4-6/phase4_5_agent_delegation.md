# Phase 4.5 — Explicit Agent Delegation

## What changed

`app/agents/delegation_tools.py` exposes the existing specialist agents through three Microsoft Agent Framework function tools:

1. `analyze_software_requirements` — returns validated `RequirementAnalysis` JSON.
2. `design_software_architecture` — accepts requirements, a model-provider name, and optional `RequirementAnalysis` JSON; returns `ArchitectureResponse` JSON with any stale review cleared.
3. `review_software_architecture` — accepts `ArchitectureResponse` JSON and returns `ArchitectureReview` JSON.

`ArchitectureOrchestrator.build_delegation_tools()` returns these tools for an optional parent `Agent(tools=...)` coordinator. The existing workflow remains the default path and is not changed by this feature.

## Contract and safety boundaries

- Tool names and descriptions are explicit and stable.
- Structured handoffs use JSON validated by the project's Pydantic schemas.
- Requirements are limited to 12,000 characters at the delegation boundary.
- Invalid structured input fails with a clear `ValueError` rather than being silently passed to a specialist.
- These are read/analysis/design tools; they do not modify repositories or execute infrastructure changes. They are registered with `approval_mode="never_require"` because they have no consequential side effects.
- This does not authenticate users, persist approval records, or make simulated approval execution production-ready.

## Example integration

```python
from agent_framework import Agent
from app.orchestrator.architecture_orchestrator import ArchitectureOrchestrator

orchestrator = ArchitectureOrchestrator()
coordinator = Agent(
    client=your_existing_model_client,
    name="ArchitectureDelegationCoordinator",
    instructions=(
        "For a new architecture request, call analyze_software_requirements first, "
        "pass its JSON output to design_software_architecture, then pass the returned "
        "architecture JSON to review_software_architecture. Summarize the final review "
        "and do not invent missing facts."
    ),
    tools=orchestrator.build_delegation_tools(),
)
```

Use the project's existing configured model client for `your_existing_model_client`; this example intentionally does not create or assume any cloud resource.

## Validation

Run:

```powershell
pytest -q tests/test_agent_delegation_tools.py tests/test_architecture_orchestrator.py
```

Then run the complete regression suite:

```powershell
pytest -q
```
