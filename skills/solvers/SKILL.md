---
name: solvers
description: Deterministic combinatorial solvers in stdlib — balance work across workers/backends (assignment, LPT), pack items under a capacity (bin-packing, FFD), and order plan steps under dependencies into a sequence + parallel waves (DAG topological scheduling, cycle-detecting). 0 cloud tokens, repeatable. Use to spread cluster work, pack tasks under a budget/capacity, or order a plan's steps — instead of asking an LLM to figure out the assignment/order.
---

# solvers — assignment, bin-packing, precedence scheduling

The OR-Tools family, in stdlib. The structured decisions the system makes —
*spread work across the cluster*, *pack items under a capacity*, *order a plan's
steps under dependencies* — are classic combinatorial problems with exact or
well-known deterministic algorithms. No LLM "figure out the order/assignment"
call: **0 cloud tokens**, same answer every time.

```bash
python -m skills.solvers.cli assign w1,w2,w3 audit:5 build:8 test:3 deploy:2
python -m skills.solvers.cli pack 10 a:4 b:7 c:3 d:6
python -m skills.solvers.cli schedule build test:build lint:build deploy:test,lint
```

- **assign_balanced(tasks, workers)** — Longest-Processing-Time-first greedy:
  balance load to minimize the makespan (within 4/3 of optimal). Spreads cluster
  work across [[cluster]] backends.
- **bin_pack(items, capacity)** — First-Fit-Decreasing: fewest bins of a given
  capacity; oversized items flagged.
- **schedule(steps, deps)** — topological order of a DAG **+ parallel waves**
  (each wave's steps have their prerequisites satisfied, so they run in parallel),
  with cycle detection. Generalises the [[conductor]]'s layer-sort into real
  precedence scheduling.

Exposed via [[llm_mcp]] as `schedule_plan` and `assign_work`. For very large
instances, `ortools` CP-SAT is a drop-in accelerator; these stdlib solvers are
the always-available, 0-dependency path.

Completes the deterministic-hybridization program (alongside [[context_budget]]
knapsack and [[nlp_deterministic]]): exact computation replacing LLM reasoning
for structured decisions.
