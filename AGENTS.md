# AGENTS.md — Botte Secrète

Guidance for AI agents (Claude Code, Codex, Cursor, Copilot, …) working in this
repo. Companion to the [README](README.md). Kept short on purpose — see linked
docs for detail.

## What this is

A multi-agent **token-optimization toolkit**: code audit, automated fixes,
per-project skill filtering, local-LLM routing, and adversarial red-teaming —
built to lean on local hardware and cheap models wherever possible.

## Setup & commands

- Language: **Python 3.10+**, standard library only (no runtime dependencies for
  the core modules). On Windows use `python` (not `python3`, which may be a stub).
- Run a module: `python -m skills.<module>.cli ...`
- Tests (94 passing):
  - Full pipeline: `python skills/test_e2e.py`
  - Module tests: `python -m skills.<module>.test_<module>` for `llm_backends`,
    `directives_audit`, `auto_router`, `skill_finder`, `bootstrap`, `infra_advisor`.
- Pre-commit checks: `python scripts/pre-commit-check.py --fast`

## Conventions (non-negotiable)

- **Stdlib-first.** Reach for a dependency only when the stdlib genuinely can't
  do it. The "laziness ladder": does it need to exist? → stdlib → native feature
  → existing dep → one line → minimum that works. Never cut input validation,
  error handling, security, or accessibility.
- **Always pass `encoding="utf-8"`** to `open` / `read_text` / `write_text`, and
  call `skills.console_utf8.force_utf8()` in scripts that print emoji — Windows
  consoles default to cp1252 and crash otherwise.
- **Compact output.** Prefer the JSON schemas in `docs/schemas/` over verbose
  markdown for inter-agent reports; group findings by file; truncate long lists.
- **Token budgets** per agent are enforced (see README "Token Budgets").
- Match the surrounding file's style; keep architecture flat.

## Layout

- `skills/` — one folder per capability, each with a `SKILL.md`.
- `scripts/` — standalone tools and hooks.
- `docs/plans/` — design docs;  `docs/schemas/` — report schemas.

## Before you finish

Run the relevant tests, keep diffs minimal, and don't commit machine-specific
generated files (e.g. `configs/llm-endpoints.json`, `.mcp.json` — both ignored).
