---
name: dashboard
layer: GOVERN
description: Generate one self-contained, timestamped HTML dashboard of the system's cost picture — routing savings (control loop), metric trends, current metrics, and the cost of outstanding fixes. Use when the user wants a single visual view of cost/savings/health over time.
---

# dashboard — the cost picture in one page

```bash
python -m skills.dashboard.cli .          # → .botte/reports/dashboard_<stamp>.html
python -m skills.dashboard.cli . --json   # the assembled data
```

Assembles live numbers from `control_loop` (routing savings), `trends` (metrics
over time), `metrics` (LOC/cost), and `fix` (cost to apply outstanding fixes) into
one timestamped HTML page, browsable any time. Exposed via [[llm_mcp]] as
`dashboard`. Related: [[control_loop]], [[trends]], [[metrics]], [[fix]], [[report]].
