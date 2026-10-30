# Phase 4.6 Milestone 3: Architecture Visualization and Reporting

## Objective

Milestone 3 transforms a `RepositoryAnalysisResult` into deterministic Mermaid architecture diagrams, structured architecture reports, and downloadable Markdown, HTML, PDF, and DOCX artifacts. It performs no repository discovery, source analysis, source execution, or repository writes.

## Architecture

- `ArchitectureVisualizer` coordinates diagram generation, structural validation, evidence mapping, and optional rendering.
- `DiagramGenerator` generates system-context, component, dependency, API, database, integration, and architecture-pattern flowcharts.
- `DiagramValidator` performs deterministic structural metadata, node, edge, evidence, and complexity validation. It does not claim full Mermaid parser validation.
- `EvidenceMapper` copies only existing `EvidenceReference` entries into diagram nodes and relationships, preserving relative paths and confidence.
- `DiagramLayout` applies configurable diagram complexity limits.
- `DiagramRenderer` uses an explicitly configured or locally discovered `mmdc` executable. Mermaid source remains canonical; missing or failed renderers produce no rendering result rather than failing visualization.
- `ReportGenerator` creates typed `ArchitectureReport` sections from analysis and visualization data.
- `ReportSections` maps findings into the required report structure and explicitly records unavailable evidence.
- `MarkdownExporter`, `HTMLExporter`, `PDFExporter`, and `DOCXExporter` present the same report data in separate export formats.
- `ArtifactManager` isolates files below a managed output root by report ID and prevents path escape, overwrite, and absolute-path result leakage.

## Diagram types

All diagrams use Mermaid `flowchart LR` syntax and stable generated node IDs. Labels are escaped and text is length-limited. No external actors, databases, integrations, consumers, tables, or relationships are added unless Milestone 2 evidence supports them.

- System context: repository, supported projects, persistence technologies, and confirmed integrations.
- Components: supported project and technology findings.
- Dependencies: resolved or recorded source-to-target findings and dependency direction.
- APIs: exposed and consumed API findings are distinguished.
- Database: database, ORM, and persistence evidence.
- Integrations: integration name, type, and confirmed/declared/inferred status.
- Patterns: only specific patterns with confidence above low and supporting static evidence.

## Rendering

SVG and PNG rendering are optional. Set `MERMAID_CLI_PATH` or pass an executable path to `DiagramRenderer`. The default discovery order is the configured path, then local `mmdc` on `PATH`.

Rendering uses local temporary files and is cleaned automatically. No repository content is sent to a remote rendering service. A missing renderer returns Mermaid source with a warning.

## Reports

The report structure includes cover, executive summary, repository overview, existing architecture, diagrams, technology stack, component/dependency analysis, API architecture, database/persistence architecture, integrations, findings, limitations, evidence references, and appendix sections. Unsupported content is omitted or explicitly described as unavailable.

`ReportConfiguration` controls the selected diagram types, section inclusion and exclusion, evidence, confidence labels, limitations, Mermaid source fallback, and rendered-diagram embedding. The generated report and every exporter enforce the same effective configuration. Section references are filtered so they cannot point to an excluded diagram type.

## Export formats

- Markdown: `.md` with Mermaid source blocks and evidence references.
- HTML: escaped document content, styled print-friendly layout, navigation, sanitized SVG or embedded PNG diagrams, and optional Mermaid source fallback.
- PDF: generated with ReportLab; embedded PNG takes precedence, with escaped text and optional Mermaid source fallback.
- DOCX: generated with python-docx; sections, headings, embedded PNG media, evidence, and optional Mermaid source fallback are included.

HTML SVG output is parsed, reduced to safe SVG elements, and stripped of script, foreign-object, event-handler, executable URL, and external-resource content before base64 embedding. PDF repository-derived text is XML/markup escaped before passing it to ReportLab paragraphs, and line breaks are preserved. PNG data is embedded directly when available. Rendered output is never embedded from a remote service.

## Dependencies

Added runtime dependencies:

- `reportlab>=4.0,<5`
- `python-docx>=1.1,<2`

Mermaid rendering still requires the optional local Mermaid CLI (`mmdc`) and Node.js/browser dependencies on the system.

## Security

- Repository code is never executed.
- Labels and report text are sanitized or escaped.
- HTML output contains no repository-derived executable markup.
- Sanitized SVG or PNG content is embedded in HTML; PDF and DOCX prefer embedded PNG.
- SVG content with script or executable/external resource payloads is not accepted unsafely.
- ReportLab text is XML escaped and control characters are removed before rendering.
- Secret patterns and connection strings are redacted from exported text.
- Absolute local source references are withheld.
- Exported models expose managed relative artifact references, not internal absolute paths.
- Artifact directories are isolated by report ID and existing files are never overwritten.
- Temporary renderer directories are removed after use.

## Limitations

Mermaid validation is structural and deterministic in this release. Full grammar validation requires a Mermaid parser or renderer. Static analysis does not establish runtime behavior, deployment topology, database tables, sequence interactions, or architecture quality. PDF and DOCX contain Mermaid source fallback when SVG/PNG rendering is unavailable.

## Testing

Run targeted tests:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
.\.venv\Scripts\python.exe -m pytest tests/repository/visualization tests/repository/reporting -q
```

The suite verifies generated diagram types, evidence integrity, structural validation, renderer fallback, report sections, HTML escaping, PDF signatures, DOCX package structure, path safety, overwrite protection, and artifact cleanup.
