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
- Tests:
  - Canonical full runner: `python scripts/run_tests.py -q`
  - Integration subset: `python skills/test_e2e.py`
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

## Tool evolution: six acceptance axes

Apply the [six-axis acceptance guide](docs/tool-improvement-axes.md) when
selecting, executing or improving skills, tools and workflows:

- **Choose correctly:** shortlist by task fit, then read each retained
  candidate's full instructions. Check operation-specific use cases, exclusions
  and prerequisites; names and lexical scores alone do not establish fit.
- **Observe consequences:** hand off affected resources, verified results,
  partial or active effects, deviations, uncertainty and evidence references.
- **Make pipelines reliable:** specify outputs and checks that each dependency
  must satisfy before its consumers proceed.
- **Resume safely:** preserve completed steps and unresolved operations; inspect
  current state before retrying so an interruption does not duplicate actions.
- **Reuse experience:** bind success and failure to source version, context and
  evidence; reassess applicability in the destination context.
- **Measure improvements:** compare the current and candidate versions on
  representative tasks; retain supported quality, reliability or cost gains
  within the task's acceptance limits.

Consult optional `effects.json` and the [effects contract](docs/capability-effects.md).
Distinguish implemented behavior from tested evidence and remaining gaps. Keep
checks proportional to the change; use existing task permissions and report
schemas. Declarations do not grant authority or verify outcomes.

Use the shared [effect review](skills/effect-review/SKILL.md) when assessing a
selected operation or handing off its results. Conductor `--review-effects`
returns compact cues; load capability-specific details only as needed. Authoring
and evidence formats remain in the [effects contract](docs/capability-effects.md).

## Botte Secrète policy
Read [`.botte/policy.md`](.botte/policy.md) before substantive work. Use Parcimonia `assess_task` when available and useful; reuse a current preflight result for homogeneous work and skip trivial/direct actions. Use scoped GitHub plans and evidence summaries when useful. If a helper is absent or abstains, continue with suitable available tools. Verify prerequisites and results; run `/checkup` after updates. See [portable instructions](docs/parcimonia-workflow.md#portable-instructions).

## Token-efficient workflows
- **Batch independent tool calls**: read multiple files, search multiple patterns, extract multiple URLs in ONE turn instead of chaining them sequentially. Each round-trip costs context tokens.
- **Never re-read after edit**: the edit tool guarantees the post-edit state. Only re-read a file when you need it for a DIFFERENT purpose.
- **Cache checkup/bench results**: if you ran `checkup .` or `bench` less than 5 min ago with no file changes since, use the cached result from `.botte-cache/` instead of re-scanning.
