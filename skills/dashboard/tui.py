"""Terminal rendering for the dashboard — same assembled data (`collect()`) as
the HTML report, rendered as ANSI panels + unicode sparklines. Reuses the
box-drawing renderer from [[demo]] so the two showcase tools look consistent.
"""

from __future__ import annotations

from skills.demo.render import Panel, render_grid, c

_BLOCKS = "▁▂▃▄▅▆▇█"


def sparkline(values: list[float]) -> str:
    """Render a short numeric series as a unicode sparkline. Flat/empty → dots."""
    vals = [v for v in values if isinstance(v, (int, float))]
    if len(vals) < 2:
        return "·" * max(1, len(vals))
    lo, hi = min(vals), max(vals)
    if hi == lo:
        return _BLOCKS[0] * len(vals)
    span = hi - lo
    return "".join(_BLOCKS[min(7, int((v - lo) / span * 7))] for v in vals)


def _metrics_lines(data: dict) -> list[str]:
    m = data.get("metrics", {}) or {}
    trends = data.get("trends", {}) or {}
    series = trends.get("series", []) or []
    lines = []
    if "loc_total" in m:
        lines.append(f"LOC        {m['loc_total']:>8,}  {sparkline([s.get('loc') for s in series])}")
    if "directive_score" in m:
        lines.append(f"directives {m['directive_score']:>8}  {sparkline([s.get('directive_score') for s in series])}")
    if "duplicate_groups" in m:
        lines.append(f"dup groups {m['duplicate_groups']:>8}")
    cost = m.get("cost", {}) or {}
    if "always_on_tokens_per_session" in cost:
        lines.append(f"always-on  {cost['always_on_tokens_per_session']:>8,} tok/session")
    return lines or ["(no metrics collected)"]


def _routing_lines(data: dict) -> list[str]:
    rs = data.get("routing_savings", {}) or {}
    if not rs.get("samples"):
        return ["(no routing history yet)"]
    return [
        f"local %       {rs.get('local_pct', 0):>6}%",
        f"escalation    {rs.get('escalation_rate', 0):>6.0%}" if isinstance(rs.get("escalation_rate"), float) else "escalation      -",
        f"success rate  {rs.get('success_rate', 0):>6.0%}" if isinstance(rs.get("success_rate"), float) else "success rate    -",
        f"tokens saved  {rs.get('tokens_saved_total', 0):>6,}",
    ]


def _fixes_lines(data: dict) -> list[str]:
    f = data.get("outstanding_fixes", {}) or {}
    if not f.get("total"):
        return ["✅ nothing outstanding"]
    lines = [f"total fixes   {f['total']:>6}"]
    for kind, n in (f.get("by_kind") or {}).items():
        lines.append(f"  {kind:<12} {n:>4}")
    totals = f.get("cost_to_apply", {}) or {}
    if "usd" in totals:
        lines.append(f"cost to fix   ${totals['usd']:.4f}")
    return lines


def _trend_deltas(data: dict) -> list[str]:
    delta = (data.get("trends", {}) or {}).get("delta_since_previous", {}) or {}
    if not delta:
        return ["(need 2+ snapshots — run `python -m skills.trends.cli snapshot .`)"]
    lines = []
    for k, d in delta.items():
        sign = "+" if d["change"] > 0 else ""
        lines.append(f"{k:<18} {d['from']} → {d['to']} ({sign}{d['change']})")
    return lines


def _loop_lines(data: dict) -> list[str]:
    loops = data.get("loops", {}) or {}
    if "error" in loops or not loops.get("events"):
        return ["(no loop telemetry yet; shadow mode is safe to enable)"]
    return [f"decisions    {loops.get('decisions', 0):>6}",
            f"stops        {loops.get('stops', 0):>6}",
            f"cache hits   {loops.get('cache_hits', 0):>6}",
            f"tokens used  {loops.get('tokens_used', 0):>6,}",
            f"avoided      {loops.get('iterations_avoided', 0):>6}",
            f"skipped      {loops.get('agents_skipped', 0):>6}",
            f"blocked      {loops.get('repetitions_blocked', 0):>6}",
            f"escalations  {loops.get('escalations', 0):>6}",
            f"cloud tokens {loops.get('cloud_tokens', 0):>6,}"]


def build_panels(data: dict) -> list[Panel]:
    return [
        Panel(c("METRICS", "bold", "cyan"), _metrics_lines(data)),
        Panel(c("ROUTING SAVINGS", "bold", "green"), _routing_lines(data)),
        Panel(c("OUTSTANDING FIXES", "bold", "yellow"), _fixes_lines(data)),
        Panel(c("LOOP OPTIMIZER", "bold", "blue"), _loop_lines(data)),
        Panel(c("TRENDS (Δ since last)", "bold", "magenta"), _trend_deltas(data)),
    ]


def render(data: dict) -> str:
    header = f"🧦 Botte dashboard — {data.get('project', '')}"
    return header + "\n\n" + render_grid(build_panels(data))
