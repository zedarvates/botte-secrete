---
name: run_contract
layer: GOVERN
description: Validate bounded Botte mission contracts, compile an exact context manifest, and emit typed inter-session handoffs. Use before an agent or MetaHarness run that must preserve scope, authority, evidence, privacy, and approval boundaries.
tags: [mission, contract, context, handoff, governance, evidence]
triggers: [mission contract, context manifest, agent handoff, bounded run]
---

# run_contract — typed mission boundaries

`run_contract` turns a free-form mission into three deterministic records:

- `botte.mission/v1` — scope, forbidden actions, authority, risk, budgets,
  evidence requirements, approval gates, rollback and context budget;
- `botte.context-manifest/v1` — exact in-repo files loaded, their hashes and
  token cost; policy and agent directives are pinned and never compressible;
- `botte.handoff/v1` — bounded status, workspace lease, checks, evidence,
  uncertainty and the next safe action.

The validator fails closed. `merge`, `deploy`, `release`, `secrets` and
`payments` remain forbidden in v1. `ACT` requires an opaque owner approval
reference and a recoverable snapshot. `SUCCEEDED` is intentionally not a valid
handoff status: work can only become `READY_FOR_REVIEW`, then an independent
reviewer returns `ACCEPT`, `REWORK` or `BLOCKED`.

## CLI

```bash
botte contract validate mission.json
botte contract context mission.json --project . --output context-manifest.json
botte contract fingerprint mission.json
```

The context compiler stores only relative repository paths. It never persists
file contents or an absolute machine path.

Schema documents live in `docs/schemas/`. Execution, workspace leasing and
independent review are integrations owned by `meta_harness`; this skill only
defines and validates their shared records.
