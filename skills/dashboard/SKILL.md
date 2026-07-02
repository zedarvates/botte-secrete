---
name: dashboard
layer: GOVERN
description: Generate one self-contained, timestamped HTML dashboard of the system's cost picture — routing savings (control loop), metric trends, current metrics, and the cost of outstanding fixes. Also renders as a live ANSI terminal view (--tui, --watch). Use when the user wants a single visual view of cost/savings/health over time, or a live terminal view they don't have to open a browser for.
---

# dashboard — the cost picture in one page

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
