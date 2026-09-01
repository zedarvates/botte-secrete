---
name: checkup
description: Run the canonical project checkup in one command — policy presence, committed semantic rules, directives health, metrics, security and drift. Use for "complete checkup", "botte doctor", after a component update, onboarding, or suspected multi-agent rule drift.
---

# checkup — the canonical project checkup ("botte doctor")

So a "complete checkup" doesn't depend on you writing a good prompt: one command
runs the standard sequence in the right order and prints a single verdict, all
local / 0 cloud tokens.

```bash
python -m skills.checkup.cli            # current dir
python -m skills.checkup.cli <project> --json
python -m skills.checkup.cli . --pr-comment   # Markdown verdict for a PR comment
python -m skills.checkup.cli . --doctor       # + machine scan + ranked top-3 opportunities
python -m skills.checkup.cli . --doctor --fresh   # re-scan for local LLM backends (not cached)
```

## `--doctor` — the one-verb assembly

`--doctor` is `checkup` plus two things it doesn't otherwise do:

- **machine scan** — is a local LLM backend reachable (LM Studio/Ollama)? via
  [[llm_backends]] `audit()`; reads the cached registry unless `--fresh`.
- **ranked top-3 opportunities** — fixes from [[fix]] `find_fixes()`, ranked by
  estimated token cost (highest first), plus any remaining drift items, capped
  at 3.

Both feed a **one-line verdict**: `✅ sain` when there's no drift and a local
backend is active, or `⚠️ N optimisation(s), ~X tokens d'opportunités`
otherwise. Pure assembly of existing modules — no new skill, no new report format.

## Sequence (cheap → deeper)

1. **policy** — is `.botte/policy.md` committed? (shared rules for devs/agents)
2. **rules** — if `.botte/rules.json` exists, verify exact source, guard,
   positive/negative probes, contradictions and semantic receipts
3. **directives** — CLAUDE.md/AGENTS.md health + stale path refs
4. **metrics** — LOC per component + always-on cost + savings framing
5. **infra** — hardware/software/MCP cluster tips (+ ASCII diagram)
6. **duplication** — stdlib AST duplicate-function scan
7. **security** — taint / data-flow scan ([[fallow_like]] `TaintAnalyzer`),
   CWE-tagged; high-severity findings become drift. 0 cloud tokens.
8. **drift** — MCP wired? directives/rules stale? policy missing? security?

Then points at the deep code audit (secrets/dead-code) for when you want it.

## Why

A component update or another dev/agent introduces **drift** — stale directives,
unwired MCP, an oversized CLAUDE.md, a missing policy. `/checkup` catches all of
it in one pass, with a fixed optimal procedure, instead of an ad-hoc prompt that
may be sub-optimal and may not prioritise local models.

## On pull requests

`--pr-comment` prints a verdict-first Markdown comment (carrying a stable marker
so a bot can edit it in place), **including the security section** — so the
taint/data-flow scan rides into CI for free. The `🧦 Botte Checkup (PR)` GitHub
Action (`.github/workflows/botte-pr-checkup.yml`) runs this on every PR and
posts/updates a single comment via `gh` — 0 cloud tokens. When a semantic rule
manifest exists, the comment includes its score and first five exact failures.
The workflow sets `BOTTE_CHECKUP_CONTEXT=github-pr`, so machine-local MCP wiring
is reported as **not applicable** instead of impossible CI drift; local checkups
still flag missing wiring. Any project that deployed botte-secrète can reuse the
same workflow.

Related: [[preflight]] (enforces prefer-local every turn), [[infra_advisor]],
[[metrics]], [[directives_audit]], [[bootstrap]].
