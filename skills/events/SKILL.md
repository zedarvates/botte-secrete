---
name: events
layer: GOVERN
description: Project-local JSONL decision log (.botte/events.jsonl) with rotation — routing, cache hits, escalations, micro-NN outputs. Demo mode, the live dashboard, and session replay read it. Use when you want to see or emit a live feed of routing/cache/escalation decisions, or when building a tool that needs to watch the belt work in real time.
---

# events — the unified decision log

One local file per project, one appended JSON line per decision until rotation
or explicit clearing removes history. Nothing else in
the pipeline needs to change what it does — it just also calls `log_event`.

```bash
python -m skills.events.cli tail .           # last 20 events
python -m skills.events.cli tail . -n 50 --json
python -m skills.events.cli log route . --field out=local --field tokens_saved=210
python -m skills.events.cli clear .
```

```python
from skills.events import log_event, read_events, tail_events, follow_events

log_event("route", project_root=".", filter=1, out="local", tokens_saved=210)
tail_events(".", n=20)
for rec in follow_events("."):   # blocking generator, for --live tools
    ...
```

## Event kinds

| kind | typical fields | emitted by |
|------|-----------------|------------|
| `route` | filter, out (local/cloud), tokens_saved, reason | `auto_router.AutoRouter.decide` |
| `cache` | hit (bool), key, tokens_saved | `cache.ProjectCache` |
| `escalate` | from, to, reason | `auto_router.AutoRouter.run` |
| `nn_out` | model, probs/class | `botte_nn` predictors |
| `fusion` | strategy, models | `auto_router.fusion` |
| `qa_outcome` | source, route, status, verification_state, evidence_count | execution adapters via `trajectory.outcome` |
| `qa_trajectory` | route, verdict, quality_score, verified_by | `trajectory.quality` |
| `qa_shadow_advice` | status, recommendation, evidence_strength, acted=false | `trajectory.quality` |

`kind` is free-form — any skill can log its own label; the table above is
just what the showcase tools (demo mode, dashboard `--watch`, replay) render
by default.

## Design

- **Best-effort, never raises.** A logging failure must never break the
  caller — same contract as `control_loop.record`.
- **Rotation** at 5 MB, keeps the newest half — same spirit as `.botte-cache/`.
- **0 tokens, 0 network in the logger.** Pure stdlib, local file only. Callers
  can export or forward its contents; local storage does not prevent disclosure.
- **Project-scoped** (`.botte/events.jsonl`), unlike `control_loop`'s
  `~/.botte/control-ledger.jsonl` which is machine-wide — events are about
  *this* project's live activity, the ledger is about tuning the router
  globally over time.

## Consequences, analysis and reuse

Read [effects.json](effects.json) when choosing between reading, appending,
following, exporting or clearing. Appending can rotate away older rows;
clearing deletes the log, and exports write potentially identifying data.
Use the task's existing authorization for the selected operation and target.

Logging is best-effort and has no durability receipt. Unsupported JSON values
are dropped without interrupting the caller. Confirm the row when its presence
matters; an absent row does not prove that the underlying action did not occur.
Repeated appends create new rows, and follower replay is not an exactly-once
trigger. Do not use either to repeat external mutations without reconciliation.

Keep secrets and raw private context out of event fields. Interpret events as
caller-supplied observations, then link independent evidence and explain gaps
in the task report. For reuse in debugging or coverage analysis, account for
rotation, malformed rows and duplicates before treating counts as complete.
See the [common contract](../../docs/capability-effects.md).

Related: [[control_loop]] (the other ledger), [[dashboard]], [[cache]].
