---
name: directives_audit
description: Audit a project's AI-agent guidance files — CLAUDE.md, AGENTS.md, .cursorrules, copilot-instructions.md, GEMINI.md, intent docs and specs, in markdown, text or HTML. Use when checking whether a repo has agent instructions, whether they are healthy/consistent, or before an agent starts work on an unfamiliar codebase. Also use when the user mentions CLAUDE.md, AGENTS.md, agent rules, "does this project have instructions", or stale/oversized directive files.
---

# directives_audit — validate AI-agent guidance files

Before an agent works on a repo, it should know which directives exist, whether
they are healthy, and — most importantly — whether they exist at all. Inspired by
shadcn/improve's "recon" step (ingest intent docs so decided tradeoffs aren't
re-flagged).

## When to use

- Checking if a project has **any** agent instructions (CLAUDE.md / AGENTS.md / …).
- Auditing existing directives for **staleness, size, format or conflicts**.
- Onboarding to an unfamiliar repo — map its instructions, intent docs and specs.
- The user mentions CLAUDE.md, AGENTS.md, agent rules, specs, or "directives".

## Run it

```bash
python -m skills.directives_audit.cli <project_dir>          # readable report
python -m skills.directives_audit.cli <project_dir> --json   # machine-readable
```

```python
from skills.directives_audit import audit
report = audit("/path/to/project")
report["has_instructions"]   # bool — the big one
report["score"]              # 0-100 directive health
report["findings"]           # severity, path, message, fix_hint
```

## What it detects

| Tool / purpose | Files |
|----------------|-------|
| Claude Code | `CLAUDE.md`, `CLAUDE.local.md`, `.claude/`, `.mcp.json` |
| Codex / OpenCode / generic | `AGENTS.md`, `.agents/**` |
| Cursor | `.cursorrules`, `.cursor/rules/**.mdc` |
| GitHub Copilot | `.github/copilot-instructions.md`, `.github/instructions/**` |
| Gemini / Antigravity | `GEMINI.md`, `.gemini/**` |
| Windsurf / Cline / Roo / Aider | `.windsurfrules`, `.clinerules`, `.roo/**`, `CONVENTIONS.md` |
| Intent (improve recon set) | `CONTEXT.md`, `DESIGN.md`, `PRODUCT.md`, `ARCHITECTURE.md`, `docs/adr/**` |
| Specs | `PRD.md`, `specs/**`, `spec/**` |

Formats: **markdown, text, HTML, .mdc, json/yaml** — some teams keep instructions
in HTML; the audit reads HTML too and flags it as a parse-friendliness issue.

## Checks

- **Missing** — no instruction file anywhere → recommends creating CLAUDE.md / AGENTS.md.
- **Oversized** — always-on instructions over ~2000 tok (warn) / ~5000 (err); re-sent every turn.
- **HTML instead of markdown** for instruction docs.
- **Broken references** — paths cited in prose docs that don't exist in the repo.
- **Empty / unreadable** directive files.
- **Multiple sources** — several instruction files that can drift apart.

Related: [[llm_backends]], `skill_project_optimizer` (per-project skill filtering).
