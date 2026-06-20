---
name: conductor
layer: DECIDE
description: Route a high-level goal to an ordered, local-first plan of capabilities — the generalised router — and optionally EXECUTE the plan's read-only steps. Reads the capability registry/curator, composes steps ordered by the system's layers (SENSE→DECIDE→ACT→REMEMBER→GOVERN→DEPLOY), annotates each local vs cloud with a concrete command, and estimates the goal's effort. The executor runs the safe analysis steps unattended and confirm-gates anything that mutates state or escalates to the cloud. Use when the user states a goal and you need to decide which botte capabilities to use in what order (or run them), or asks "how should I approach X with this toolkit".
---

# conductor — goal → ordered plan of capabilities

The router, generalised: not "which model tier?" but "given this **goal**, which
capabilities, in which order, and what stays local?". The plan is the product —
you (or the agent) execute it; the Conductor never runs anything itself.

```bash
python -m skills.conductor.cli "test my desktop app and report crashes"
python -m skills.conductor.cli "reduce token cost and deploy on my project" --json

# Execute the plan (read-only steps run; mutating/cloud steps are gated):
python -m skills.conductor.cli "audit my project and report metrics" --execute
python -m skills.conductor.cli "..." --execute --dry-run      # preview, runs nothing
python -m skills.conductor.cli "..." --execute --confirm      # also run gated steps
```

## How it plans

1. **Curate** — picks the capabilities relevant to the goal ([[capabilities]]
   curator, local lexical match, 0 tokens).
2. **Order** — sorts them by the system's layers (SENSE → DECIDE → ACT →
   REMEMBER → GOVERN → DEPLOY): understand → decide → act → remember.
3. **Annotate** — each step gets a concrete command, a local/cloud flag, and the
   reason it's there.
4. **Estimate** — the goal's effort tier ([[auto_router]]) tells you whether any
   step's reasoning will escalate to the cloud.

Output: an ordered list of steps, **0 cloud tokens** to produce. It composes the
module collection into a coherent plan per goal — the conductor of the system.

## Executing the plan

The plan can be *run*, not just read. The executor classifies every step:

- **safe** — read-only analysis (`directives_audit`, `metrics`, `infra_advisor`,
  `checkup`, `cluster`, `llm_backends`) → runs unattended, 0 cloud tokens.
- **gated** — mutates state, generates artifacts, or escalates to the cloud →
  runs only with `--confirm` / `confirm=true`.
- **needs_args** — the command still has an unfilled `<placeholder>` → never runs.

`--dry-run` classifies everything and runs nothing (a preview). A failing step
yields a non-zero exit so CI can react. The runner is injectable, so the
behaviour is fully unit-tested without spawning subprocesses.

Exposed via [[llm_mcp]] as `conduct` (plan) and `execute_plan` (plan + run safe
steps). Built on [[capabilities]], [[auto_router]]; pairs with the [[control_loop]]
(measure savings → adapt the routing).
