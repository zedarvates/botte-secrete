---
name: checkup
description: Run the standard project checkup for policy presence, directives, metrics, infrastructure, duplication, security candidates and drift. Use after a component update, when onboarding a project, or when the user requests a checkup or botte doctor.
---

# checkup — the canonical project checkup ("botte doctor")

One command assembles local diagnostics and prints their findings. It does not
apply suggested fixes or establish that all project behavior is correct.

```bash
python -m skills.checkup.cli            # current dir
python -m skills.checkup.cli <project> --json
python -m skills.checkup.cli . --pr-comment   # Markdown verdict for a PR comment
python -m skills.checkup.cli . --doctor       # + machine scan + ranked top-3 opportunities
python -m skills.checkup.cli . --doctor --fresh   # re-scan for local LLM backends (not cached)
python -m skills.checkup.cli . --save both        # save Markdown/HTML reports
```

## `--doctor` — the one-verb assembly

`--doctor` is `checkup` plus two things it doesn't otherwise do:

- **machine scan** — is a local LLM backend reachable (LM Studio/Ollama)? via
  [[llm_backends]] `audit()`; uses the cached registry when non-empty, otherwise
  probes and refreshes it. `--fresh` requests a refresh explicitly. The regular
  checkup's infra assessment can also refresh an empty registry.
- **ranked top-3 opportunities** — fixes from [[fix]] `find_fixes()`, ranked by
  estimated token cost (highest first), plus any remaining drift items, capped
  at 3.

Both feed a **one-line verdict** and action estimates. Inspect the underlying
`available`, error and drift fields: the verdict can look healthy when machine
assessment is unavailable. Estimates are not measured savings or billed usage.

## Sequence (cheap → deeper)

1. **policy** — does `.botte/policy.md` exist? The field is named
   `policy_committed`, but the implementation does not check Git tracking.
2. **directives** — CLAUDE.md/AGENTS.md health + stale path refs
3. **metrics** — LOC per component + always-on cost + savings framing
4. **infra** — hardware/software/MCP cluster tips (+ ASCII diagram)
5. **duplication** — stdlib AST duplicate-function scan
6. **security** — taint / data-flow scan ([[fallow_like]] `TaintAnalyzer`),
   CWE-tagged; high-severity findings become drift. 0 cloud tokens.
7. **malicious patterns** — suspicious code candidates; false positives remain possible.
8. **micro-NN** — grounding assessment when the project has model files.
9. **host prefix** — estimates of runtime context overhead, partly heuristic.
10. **drift** — combines the available findings; does not prove absence of issues.

Then points at the deep code audit (secrets/dead-code) for when you want it.

## Why

A component update or another dev/agent introduces **drift** — stale directives,
unwired MCP, an oversized CLAUDE.md, a missing policy. `/checkup` makes the
available checks repeatable and points to findings for verification.

## Consequences, verification and reuse

Read [effects.json](effects.json), the [infra declaration](../infra_advisor/effects.json)
and the [backend declaration](../llm_backends/effects.json) for inherited effects.
Diagnostics read project files and some host
metadata, consume CPU/I/O and may probe loopback services and write the toolkit
backend registry when its cache is empty. Optional imported components can create
local state directories. The CLI does not run model inference or apply fixes.

`--save` writes reports under the target project's `.botte/reports/`. Output may
contain paths, code snippets, configuration metadata and estimates. Review its
recipient and task scope before sharing. `--pr-comment` only prints Markdown;
it returns before report saving, even if `--save` is also supplied.

A zero CLI exit means the report was produced, including when drift exists.
Record scanner availability and errors alongside findings, and verify important
candidates against source and tests. Keep the exact checkout and runtime context
with these observations. On retry, check whether sources changed and
whether probes or report writes already happened. No automatic fix or rollback
is implied by the report.

For reuse as a CI gate, define explicit thresholds and treatment of unavailable
scanners; test both defective fixtures and missing dependencies. Publication
needs the existing repository workflow scope. See the
[common contract](../../docs/capability-effects.md).

## On pull requests

`--pr-comment` prints a verdict-first Markdown comment (carrying a stable marker
so a bot can edit it in place), **including the security section** — so the
taint/data-flow scan rides into CI for free. The `🧦 Botte Checkup (PR)` GitHub
Action (`.github/workflows/botte-pr-checkup.yml`) runs this on every PR and
posts/updates a single comment via `gh` — 0 cloud tokens, no extra dependencies.
The workflow sets `BOTTE_CHECKUP_CONTEXT=github-pr`, so machine-local MCP wiring
is reported as **not applicable** instead of impossible CI drift; local checkups
still flag missing wiring. Any project that deployed botte-secrète can reuse the
same workflow.

Related: [[preflight]] (enforces prefer-local every turn), [[infra_advisor]],
[[metrics]], [[directives_audit]], [[bootstrap]].
