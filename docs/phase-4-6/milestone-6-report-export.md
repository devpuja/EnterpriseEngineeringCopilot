# Phase 4.6 Milestone 6: Report Export

## Objective and scope

Milestone 6 turns the existing analysis, visualization, synthesis, and review results into one validated architecture report that can be exported as Markdown, HTML, PDF, or DOCX. It does not add API endpoints, orchestration, authentication, deployment, or Milestone 7 functionality.

## Existing report architecture reused

The implementation extends the Milestone 3 `ArchitectureReport`, `ReportConfiguration`, `ReportSections`, `ReportGenerator`, `ArtifactManager`, and four existing exporters. It also reuses the existing `ArchitectureDiagram` objects and local `DiagramRenderer`; report generation does not rerun repository discovery, analysis, synthesis, review, or diagram rendering.

## Canonical report model and source integration

`ArchitectureReport` remains the single canonical model. It now includes safe repository metadata, source result IDs, structured evidence, the source synthesis and review results, report warnings and limitations, the configured diagrams, and normalized sections. The unified synthesis diagram is added to the same diagram list while preserving the existing seven-value `DiagramType` enum; it is identified by its stable `unified_architecture` diagram ID.

`ReportGenerator.generate(analysis, visualization, configuration=None, *, synthesis=None, review=None)` preserves the existing call shape and accepts optional Milestone 4 and 5 results. It checks visualization-to-analysis, synthesis-to-analysis, and review-to-synthesis/analysis IDs and rejects mismatches. When synthesis or review is omitted for backward compatibility, the report explicitly says that the corresponding results are unavailable and records a warning.

Sections are built in one deterministic order and include the repository overview, architecture diagrams, synthesized components/relationships/data flows/external systems, review outcome/findings/strengths, recommendations, evidence, and limitations. The executive summary incorporates synthesis and review results when supplied.

## Validation and configuration

`validate_report` checks required metadata and sections, stable section ordering, source IDs, configuration consistency, unique diagram/evidence IDs, safe relative evidence paths, diagram references, synthesis component/relationship/data-flow references, review component/evidence/relationship/data-flow references, and recommendation presence. Invalid configuration values, conflicting include/exclude sections, and invalid source references raise `ReportValidationError` with a field-oriented message.

All exporters validate the report before writing. Configuration filtering occurs while the canonical report is prepared, not independently in exporters. Evidence, confidence, limitations, Mermaid source, rendered diagrams, selected diagram types, included sections, and excluded sections are reflected in the report data consumed by every format. Conflicting include/exclude values are rejected.

## Exporters and cross-format consistency

- **Markdown:** adds metadata and a table of contents, uses safe text handling, emits Mermaid fences when enabled, and writes valid rendered PNGs as managed relative image assets.
- **HTML:** creates a standalone responsive and print-friendly document with navigation; repository text is escaped, SVG is sanitized before embedding, PNGs are checked, and Mermaid source is the local fallback. No remote scripts, stylesheets, or rendering services are used.
- **PDF:** uses the existing ReportLab dependency, escaped Paragraph text, a cover page, a contents list, headers/footers, and page numbers. Valid PNGs are embedded; Mermaid source is retained as a fallback.
- **DOCX:** uses the existing python-docx dependency, editable heading and list structures, a cover and contents list, header/footer and page-number field, and embedded PNGs with Mermaid fallback.

Each exporter reads the same validated `ArchitectureReport.sections` and `ArchitectureReport.diagrams`; severity, status, summaries, evidence IDs, and recommendations are not recomputed by format.

## Diagram rendering and artifact management

The report generator reuses renderer output already present in the visualization/synthesis results. Rendering remains local through the configured Mermaid CLI in the existing renderer; no exporter calls a remote rendering service or independently regenerates diagrams. HTML can embed sanitized SVG or PNG; Markdown, PDF, and DOCX embed validated PNG where supported. Mermaid source is preserved when configured, and missing/invalid rendering produces an explicit export warning.

`ArtifactManager` keeps output in per-report directories, generates UUID-based report filenames, restricts attachment names and extensions, rejects traversal, prevents overwrite, enforces the configured size ceiling, and returns relative managed references. For local analyses, exporters reject output roots inside the source repository. Export results record format, filename, MIME type, size, and relative artifact location.

## Security and error handling

Repository-derived strings and configuration metadata are redacted for common credential patterns and local absolute paths. Exporters escape HTML/ReportLab input, sanitize SVG, validate PNGs, avoid external resources, and do not execute repository code. Artifact paths are constrained to the managed output root; write, validation, and exporter failures return a failed result with a useful warning rather than a success-shaped fallback.

## Dependencies and known limitations

No dependency manifest changes were needed. The implementation uses the existing ReportLab, python-docx, Pillow-through-ReportLab, Pydantic, and Mermaid CLI support.

PDF and DOCX embed PNG rather than SVG. Markdown embeds PNG assets rather than SVG. If no rendered image is available, Mermaid source is the fallback when enabled. The report exporter itself does not invoke Mermaid; upstream visualization is responsible for producing rendered results. The output directory remains an explicit caller-supplied managed location.

## Tests

Run the report tests and complete suite with:

```powershell
.venv\Scripts\python.exe -m pytest tests\repository\reporting -q
.venv\Scripts\python.exe -m pytest -q
```

Verified in the current workspace:

- Repository milestone tests, including Milestones 2-6: **79 passed, 2 skipped**.
- Complete pytest suite: **226 passed, 2 skipped**.

Coverage includes source ID mismatch rejection, canonical section order, all eight diagrams with synthesis, configuration filtering, secure artifact handling, rendered image fallback/embedding, PDF signature, DOCX package validity, and shared review content across all four exports.
