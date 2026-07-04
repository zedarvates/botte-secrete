---
name: dashboard
description: "Live dashboard for botte-secrete metrics — Decision Ladder, Universal Compressor, AutoMemory."
version: 1.0.0
---

# Dashboard Skill

Live metrics visualization for botte-secrete.

## Components

- `index.html` — Dashboard UI
- `api.py` — HTTP API (`/api/stats`, `/`)
- `cron_hook.py` — Periodic notifications

## Usage

```bash
# Start API server
python3 -m skills.dashboard.api

# View dashboard
open http://localhost:8765

# CLI stats
python3 -c "from skills.dashboard.api import load_metrics; print(load_metrics())"
```

## Metrics Served

- `tests_passed` — Total test count
- `lines_saved` — Lines avoided via decision ladder
- `avoidable_pct` — % of tasks that didn't need new code
- `by_rung` — Breakdown by decision ladder rung
- `compressor` — Compression stats
- `memory_entries` — AutoMemory entry count