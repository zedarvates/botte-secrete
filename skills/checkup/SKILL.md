---
name: checkup
description: Run the canonical, already-optimal project checkup in one command — policy presence, directives health, per-component metrics, infra tips, duplication, and drift detection — so you never have to hand-write a good checkup prompt. Use when the user says "do a complete checkup", after a component update, when onboarding to a project, or when multiple agents/devs may have caused drift.
---

# checkup — the canonical project checkup

So a "complete checkup" doesn't depend on you writing a good prompt: one command
runs the standard sequence in the right order and prints a single verdict, all
local / 0 cloud tokens.

```bash
python -m skills.checkup.cli            # current dir
python -m skills.checkup.cli <project> --json
```

## Sequence (cheap → deeper)

1. **policy** — is `.botte/policy.md` committed? (shared rules for devs/agents)
2. **directives** — CLAUDE.md/AGENTS.md health + stale path refs
3. **metrics** — LOC per component + always-on cost + savings framing
4. **infra** — hardware/software/MCP cluster tips (+ ASCII diagram)
5. **duplication** — stdlib AST duplicate-function scan
6. **drift** — MCP wired? directives stale/oversized? policy missing?

Then points at the deep code audit (secrets/dead-code) for when you want it.

## Why

A component update or another dev/agent introduces **drift** — stale directives,
unwired MCP, an oversized CLAUDE.md, a missing policy. `/checkup` catches all of
it in one pass, with a fixed optimal procedure, instead of an ad-hoc prompt that
may be sub-optimal and may not prioritise local models.

Related: [[preflight]] (enforces prefer-local every turn), [[infra_advisor]],
[[metrics]], [[directives_audit]], [[bootstrap]].
