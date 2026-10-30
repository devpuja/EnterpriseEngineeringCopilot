# Phase 4.6 Milestone 4: Architecture Synthesis

## Objective

Milestone 4 converts a `RepositoryAnalysisResult`, optionally paired with a matching
`ArchitectureVisualizationResult`, into a traceable architecture synthesis model.
It adds no repository discovery, source analysis, repository reads, execution, report
generation, HTTP endpoints, or agent orchestration.

## Models and service

The synthesis package defines:

- `ArchitectureComponent`, with stable ID, category, responsibility, project/file references, evidence IDs, and confidence.
- `ArchitectureRelationship`, with source and target component IDs, relationship type, evidence, confidence, and confirmed/inferred status.
- `ArchitectureDataFlow`, with source and target IDs, interaction type, evidence, confidence, and status.
- `ExternalSystem` for evidence-backed integrations.
- `ArchitectureSynthesisResult` (`ArchitectureSynthesisModel` is an alias) containing the original analysis ID, repository metadata, synthesized findings, summary, warnings, limitations, metadata, and unified diagram.
- `ArchitectureSynthesizer`, which implements the focused `ArchitectureSynthesizerContract`.

## Derivation

The repository boundary is created as the synthesis root. Project findings become project
components; entry points, exposed API boundaries, persistence findings, resolved dependencies,
and external integrations become components or relationships only when matching evidence exists.
External integrations are not represented as internal components.

Resolved dependencies are marked confirmed. Unresolved dependencies and persistence/integration
interactions without stronger evidence are marked inferred. Static evidence never becomes a claim
about runtime communication, data movement, execution order, or deployment topology.

Evidence IDs are copied only from the original analysis result. Component and finding confidence
is preserved where available; API and aggregate findings derive confidence from the referenced
evidence. Missing evidence produces low confidence or an explicit warning.

## Mermaid output

`ArchitectureSynthesizer` produces one `unified_architecture` diagram alongside the existing seven
Milestone 3 diagrams. It uses `flowchart LR`, deterministic SHA-1-derived node IDs, escaped and
truncated repository-derived labels, internal nodes and external-system nodes, and evidence maps.
Default limits are 30 nodes and 30 edges; configurable limits generate warnings when content is
truncated. Existing `DiagramValidator` rules validate node uniqueness, edge metadata, complexity,
evidence references, and Mermaid source structure. Validation is structural, not a full Mermaid
grammar parse.

## Limitations

Static evidence may be incomplete, and relationships not established by code or configuration are
omitted or marked inferred. Runtime requests, database table movement, sequencing, deployment
nodes, and network topology are not inferred. The visualization input is optional and mismatched
visualizations are ignored.

## Testing

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
.\.venv\Scripts\python.exe -m pytest tests/repository/visualization/test_milestone4_architecture_synthesis.py -q
.\.venv\Scripts\python.exe -m pytest tests/repository/analysis tests/repository/visualization tests/repository/reporting -q
```
