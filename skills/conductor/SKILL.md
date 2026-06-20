---
name: conductor
layer: DECIDE
description: Route a high-level goal to an ordered, local-first plan of capabilities — the generalised router. Reads the capability registry/curator, composes steps ordered by the system's layers (SENSE→DECIDE→ACT→REMEMBER→GOVERN→DEPLOY), annotates each local vs cloud with a concrete command, and estimates the goal's effort. Use when the user states a goal and you need to decide which botte capabilities to use in what order, or asks "how should I approach X with this toolkit".
---

# conductor — goal → ordered plan of capabilities

The router, generalised: not "which model tier?" but "given this **goal**, which
capabilities, in which order, and what stays local?". The plan is the product —
you (or the agent) execute it; the Conductor never runs anything itself.

```bash
python -m skills.conductor.cli "test my desktop app and report crashes"
python -m skills.conductor.cli "reduce token cost and deploy on my project" --json
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
26-module collection into a coherent plan per goal — the conductor of the system.

Exposed via [[llm_mcp]] as `conduct`. Built on [[capabilities]], [[auto_router]];
the natural next layer is a control loop (measure savings → adapt the routing).
