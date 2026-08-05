---
name: dashboard
layer: GOVERN
description: Generate one self-contained, timestamped HTML dashboard of the system's cost picture — routing savings (control loop), metric trends, current metrics, and the cost of outstanding fixes. Also renders as a live ANSI terminal view (--tui, --watch) and serves a live HTTP API (api.py). Use when the user wants a single visual view of cost/savings/health over time, or a live terminal view they don't have to open a browser for.
version: 1.0.0
---

# Dashboard Skill

Live metrics visualization for botte-secrete — one data source, three views
(timestamped HTML report, ANSI TUI, live HTTP API).

## Usage

```bash
python -m skills.dashboard.cli .              # → .botte/reports/dashboard_<stamp>.html
python -m skills.dashboard.cli . --json        # the assembled data
python -m skills.dashboard.cli . --tui         # same data, rendered as ANSI panels once
python -m skills.dashboard.cli . --watch       # re-render every --interval seconds (default 5s)
```

Assembles live numbers from `control_loop` (routing savings), `trends` (metrics
over time), `metrics` (LOC/cost), and `fix` (cost to apply outstanding fixes) into
one timestamped HTML page, browsable any time. Exposed via [[llm_mcp]] as
`dashboard`. Related: [[control_loop]], [[trends]], [[metrics]], [[fix]], [[report]],
[[demo]] (shares the same ANSI panel renderer), [[events]].

## `--tui` / `--watch`

`skills/dashboard/tui.py` renders the exact same `collect()` dict the HTML
report uses — one data source, two views. `--tui` prints one frame; `--watch`
loops, re-collecting and re-rendering every `--interval` seconds (Ctrl+C to
stop) — the metrics/routing/fixes counterpart to `demo --live`'s routing feed.
Metric panels include unicode sparklines (`▁▂▅▇`) sourced from `trends.show()`'s
last 10 snapshots — run `python -m skills.trends.cli snapshot .` periodically
(e.g. from CI) to build up history.

## `--fleet` — every project on this machine, one view

```bash
python -m skills.dashboard.cli fleet add /path/to/project    # opt-in registry
python -m skills.dashboard.cli fleet list
python -m skills.dashboard.cli fleet remove /path/to/project
python -m skills.dashboard.cli --fleet [--json]               # aggregate them all
```

`~/.botte/fleet.json` is an **explicit opt-in registry**, not a filesystem
scan — nothing gets touched unless you `fleet add` it. `--fleet` runs
`collect()` on every registered project and sums LOC / tokens saved /
outstanding fixes; a project that's vanished or errors out is reported
under `errored`, not silently dropped or a crash. See `skills/dashboard/fleet.py`.

## Live HTTP API

- `index.html` — Dashboard UI
- `api.py` — HTTP API (`/api/stats`, `/`)
- `cron_hook.py` — Periodic notifications

```bash
# Start the loopback-only API server
python -m skills.dashboard.api

# View dashboard
open http://127.0.0.1:8765

# CLI stats
python -c "from skills.dashboard.api import load_metrics; print(load_metrics())"

# Build the sanitized GitHub Pages artifact
python scripts/generate_public_dashboard.py --output .botte-cache/public-dashboard
```

The live server binds to `127.0.0.1` by default and reads local operational
metrics. The static generator deliberately excludes local Memory Hub and
Decision Ladder data; CI can publish only the repository test summary. The
tracked `docs/dashboard.html` is a launcher and never embeds demo values.

### Metrics served

- `tests_passed` / `tests_failed` — Latest observed `scripts/run_tests.py` result
- `tests_status` / `tests_partial` / `tests_stale` — Result provenance and freshness
- `lines_saved` — Lines avoided via decision ladder
- `avoidable_pct` — % of tasks that didn't need new code
- `by_rung` — Breakdown by decision ladder rung
- `compressor` — Compression stats
- `memory_entries` / `memory_projects` — Governed Memory Hub aggregate counts
- `memory_by_status` / `memory_by_asset` — Aggregate lifecycle/type counts only
- `legacy_memory_entries` — AutoMemory count during the migration window
