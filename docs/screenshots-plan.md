# Public documentation visuals

This page records how the README visuals are sourced and regenerated. Public
images must represent real product output or a clearly labelled synthetic
fixture. They must not contain credentials, private paths, machine identifiers,
local memory content, or proprietary project data.

## Visual inventory

| File | Source | Status |
|---|---|---|
| `docs/assets/dashboard-overview.png` | Sanitized static public dashboard | Product capture |
| `docs/assets/routing-demo.svg` | Final frame of the fixed offline demo | Deterministic fixture capture |
| `docs/assets/benchmark-compression.svg` | Current bundled benchmark result | Reproducible measured chart |
| README routing diagram | Mermaid embedded in Markdown | Maintained architecture schema |
| README architecture diagram | Mermaid embedded in Markdown | Maintained boundary schema |

## Regenerate the SVG visuals

```bash
python scripts/generate_docs_visuals.py
```

The generator runs the bundled benchmark and the fixed demo in-process. It uses
only the repository and Python standard-library rendering, then writes both SVGs
to `docs/assets/`.

Review the diff after regeneration. A changed benchmark graphic needs an
explanation in the pull request; it must not be accepted as an unexplained
marketing improvement.

## Regenerate the dashboard source

```bash
python scripts/generate_public_dashboard.py --output .botte-cache/docs-dashboard
```

The public build contains a copy of the UI and a filtered `dashboard-data.json`.
It excludes local operational metrics and memory contents. Inspect the JSON
before capture, especially when the dashboard schema changes.

On Windows with Microsoft Edge installed, capture the generated `index.html` in
headless mode at 1440 × 1050. On other platforms, use an equivalent Chromium
command. The checked-in image is documentation, not a runtime artifact.

## Review checklist

- Text is readable at GitHub's normal README width.
- The image has a useful alt description where embedded.
- Metrics state whether they are measured, synthetic, partial, or sanitized.
- The source command still runs from a clean clone.
- No private or machine-specific data appears in the image metadata or pixels.
- Mermaid diagrams render on GitHub and match `docs/ARCHITECTURE.md`.
