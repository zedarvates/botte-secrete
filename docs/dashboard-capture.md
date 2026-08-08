# Dashboard capture and publication

The dashboard has two distinct data modes:

- **local operational view** — may include project events, metrics, and memory
  status; keep it local;
- **public static view** — contains only repository-safe test metadata and zeroed
  local operational fields.

Build the public view with:

```bash
python scripts/generate_public_dashboard.py --output .botte-cache/public-dashboard
```

Open `.botte-cache/public-dashboard/index.html` in a browser or serve that
directory with a local static server. The UI falls back to the adjacent
`dashboard-data.json` when no API is available.

Before publishing or capturing it:

1. Inspect `dashboard-data.json`.
2. Confirm `local_metrics_included` is `false`.
3. Confirm the test metadata identifies whether the result is partial or stale.
4. Capture only the public artifact, never the live local API.
5. Record the generation date in the commit or pull-request description.

The canonical README screenshot process and visual inventory live in
[screenshots-plan.md](screenshots-plan.md). Runtime dashboard commands live in
[`skills/dashboard/SKILL.md`](../skills/dashboard/SKILL.md).
