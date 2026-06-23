---
name: docs_steward
description: Scoped documentation map for multi-component projects (server + client + tools + …). Detects components, classifies every doc as global vs component-scoped, and produces a per-component index (DOCS.md) listing local docs + links to the relevant global docs — so an LLM coder bounded to one component loads only its scope, not every other component's documentation. Frames token cost (full project docs vs scoped load) and treats .md as LLM-facing, .html as human reference. Use when a project has several components and you want to cut the docs an agent must read, or asks how to organise docs for a monorepo.
---

# docs_steward — the right docs, at the right scope

A monorepo accumulates docs at several scopes: **global** docs at the root, and
**component** docs inside each component's folder. When an LLM coder is *bounded*
to one component (e.g. the server), loading every other component's docs wastes
tokens every turn. The steward builds a **scoped map** so each bounded coder
loads only its own docs **+ links to the relevant global docs**.

```bash
python -m skills.docs_steward.cli map   .                 # the scoped docs map
python -m skills.docs_steward.cli index . --component server   # preview server/DOCS.md
python -m skills.docs_steward.cli index . --write         # write a DOCS.md per component
python -m skills.docs_steward.cli tasks .                 # lifecycle: finished tasks + report sprawl
python -m skills.docs_steward.cli prune . --write         # strip done tasks (archived, not lost)
python -m skills.docs_steward.cli reports . --keep 5 --archive   # tidy .botte reports
```

## How it maps

1. **Detect components** — top-level dirs with a manifest (`package.json`,
   `pyproject.toml`, `go.mod`, …), known names (server/client/api/tools/…), or
   code; monorepo containers (`apps/`, `packages/`, `services/`) expand to their
   children. Pure-doc/asset dirs are never components.
2. **Classify docs** — every `.md`/`.mdx`/`.rst`/`.txt`/`.html` is assigned to the
   deepest component it lives under, else it's **global**.
3. **Scope + frame** — each component gets its local docs, links to the global
   (LLM-facing) docs, and a token cost: *scoped load* (local + globals) vs *all
   project docs*. `.md` = load; `.html` = human reference (linked, not loaded).
4. **Index (confirm-gated)** — `index --write` drops a `DOCS.md` in each component
   telling a bounded coder exactly what to load. Preview by default; `--write`
   to commit the files.

Output: a JSON map, 0 cloud tokens to produce. Exposed via [[llm_mcp]] as
`docs_map`. Related: [[directives_audit]] (agent-guidance file health),
[[metrics]] (per-component cost), [[checkup]].

## Docs lifecycle (finished tasks + report sprawl)

Finished work shouldn't keep costing tokens. `lifecycle.py` adds two
confirm-gated jobs (preview by default, act only on `--write`/`--archive`):

- **tasks/plans** — `scan_tasks` finds checkbox markdown (`- [ ]` / `- [x]`) and
  counts open vs done + the token waste of done items still in-file. `prune`
  strips done items (preserving them in `.botte/archive/<name>.done.md` — nothing
  is lost) and moves fully-done plans out of the working tree.
- **reports** — `report_hygiene`/`reports --archive` keep the N most recent of
  each `.botte` report and move the rest to `.botte/reports/archive/`.

Read-only summary via the `docs_lifecycle` MCP tool (`lifecycle_report`); the
prune/archive actions stay CLI-only and confirm-gated.

Next in the same module: an md↔html policy and a docs-drift check in /checkup.
