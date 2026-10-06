# Architecture

## Sources of truth

- Report contract: `schemas/report.schema.json`
- Topic taxonomy: `config/topic_taxonomy_v2.json`
- Legacy taxonomy aliases: `config/taxonomy_aliases.json`
- Concept aliases and cross-category hub rules: `config/concept_aliases.json`
- Operational topic state: `data/topic_db.json`
- Published report bodies: `outputs/*_Report.json`
- Curated report concept additions/exclusions: `data/knowledge_annotations.json`
- Curated semantic relationships: `data/knowledge_edge_overrides.json`

The following are derived and must not be edited by hand:

- `data/topic_db.sqlite`
- `data/manifest.json`
- `public/latest.json`
- `public/reports.json`
- `public/api/v1/*.json`
- rendered report HTML and PDF

## Publication boundary

1. Select and generate a report.
2. Normalize and validate the report body.
3. Render HTML and PDF into a temporary directory.
4. Validate the PDF page count.
5. Update operational state and derived public data.
6. Build and validate the knowledge graph data.
7. Commit the complete package to `report-staging`.
8. A separate workflow promotes the package to `main` after the publication gate.
9. The publication workflow verifies both the catalog entry and PDF on GitHub Pages.

No incomplete generation may update the remote public catalog. JSON writes use atomic
replacement so interrupted local writes do not leave truncated files.

## Module boundaries

- `scripts/run_daily_report.py`: compatibility CLI and orchestration
- `scripts/generate_report.py`: OpenAI transport and wire-format normalization
- `scripts/report_pipeline/json_store.py`: atomic JSON persistence
- `scripts/report_pipeline/taxonomy.py`: taxonomy validation and migration
- `scripts/report_pipeline/catalog.py`: stable IDs and public catalog transforms
- `scripts/report_pipeline/knowledge_graph.py`: graph model and integrity rules
- `scripts/report_pipeline/concept_extractor.py`: evidence-backed report concept index

New domain logic belongs in `scripts/report_pipeline/`, not directly in the CLI.

## Knowledge graph evolution

The graph has a deterministic taxonomy hierarchy plus evidence-backed shared concept
nodes. Concept extraction runs after report publication and never changes the OpenAI
response contract. Each tag records its source field, and a shared concept must occur in
at least two reports across at least two main categories. Broad curated pattern hubs are
bounded to prevent an unreadable all-to-all graph.

A direct semantic report-to-report edge is publishable only when it has a relation type,
score, human-readable explanation, and evidence. Future embedding or model-assisted
scoring should generate candidates in a separate cache; only reviewed or automatically
verified edges should enter the public graph.

Every graph build records `schema_version`, `taxonomy_version`, and `algorithm_version`.
Changing the public shape requires a new API version instead of silently changing `v1`.

`knowledge-map.html` and `knowledge-map.js` are a dependency-free SVG client of the
versioned public graph. Pure indexing, scoring, and layout calculations live in
`knowledge-map-core.mjs` so they can be tested without a browser. The overview renders
only category nodes; selecting a category progressively reveals taxonomy, reports, and
shared concepts. The detail panel is the authoritative navigation surface for opening
reports and inspecting the exact cross-category report set behind a concept.

## Storage policy

Generated binaries currently remain in Git for GitHub Pages compatibility. This does not
scale indefinitely. Before the repository approaches platform size limits, move PDF/HTML
assets to a deployment branch, Pages artifact, or object storage. Keep report metadata and
the knowledge graph small, versioned, and rebuildable from canonical report JSON.

`scripts/audit_project.py` reports generated output sets that are not referenced by the
public catalog. It does not delete them automatically; archival and deletion require an
explicit review.
