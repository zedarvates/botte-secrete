---
name: demo
layer: GOVERN
description: Live ANSI dashboard of the belt's decisions — routing, token savings, micro-NN outputs, escalations, cache hits — either a built-in scripted scenario (no LLM, no network, works on a bare machine) or tailing a real project's event log. Use when the user wants to see/demo what the routing belt is doing, record a README GIF, or watch live decisions while an agent works.
---

# demo — watch the belt decide, live

Four panels, refreshed as decisions happen: **ROUTING**, **SAVINGS**,
**MICRO-NN**, **ESCALATIONS**. Reads from [[events]] — same data source as
`dashboard --watch` and session replay.

```bash
python -m skills.demo.cli scripted                    # built-in scenario, ~4s total
python -m skills.demo.cli scripted --speed 0 --no-clear # dump all frames, no timing
python -m skills.demo.cli live .                       # tail a real project while an agent works
python -m skills.demo.cli replay events.json --speed 0.3
```

## Two modes, same renderer

- **`scripted`** — 6 fixed steps (`scenario.py`) covering every filter of the
  belt: micro-NN routing, a deterministic classifier, a cache hit, a cloud
  escalation, a verification-failure escalation, an anomaly-detector output.
  Deterministic, no dependency on a running LLM or `.botte/events.jsonl` —
  this is the mode for a README GIF or a cold-machine walkthrough.
- **`live`** — tails a real project's `.botte/events.jsonl` (written by
  [[auto_router]], [[cache]], …) while an agent works. Genuine decisions,
  genuine numbers.

Both funnel through `build_panels(events) -> list[Panel]` and
`render_grid(panels) -> str`, so a third source (e.g. a captured replay file)
is just another list of event dicts — see `replay`.

## Design

- Pure stdlib ANSI (`render.py`) — no `rich`/`textual` dependency, degrades to
  plain text when `NO_COLOR` is set or stdout isn't a TTY.
- Panels trim to a fixed width so the layout never breaks on a long task
  description.
- `--no-clear` disables the screen-clear escape codes — use it for piping
  frames into a file (recording) or in this test harness.

Related: [[events]] (the data source), [[dashboard]] (the report counterpart).
