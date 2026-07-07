"""Statusline — one-line summary of the belt's session activity, for embedding
in a terminal statusline (Claude Code's `statusLine` hook, tmux, a shell
prompt, …). Reads the same `.botte/events.jsonl` as [[demo]] and [[dashboard]]
— passive, 0 tokens, no extra state to maintain.
"""

from __future__ import annotations

from pathlib import Path


def summarize(project_root: str | Path = ".") -> dict:
    """Aggregate the session's events into the numbers a statusline shows."""
    from skills.events import read_events
    events = read_events(project_root)
    saved = sum(int(e.get("tokens_saved", 0)) for e in events)
    cache_hits = sum(1 for e in events if e.get("kind") == "cache" and e.get("hit"))
    local_routes = sum(1 for e in events if e.get("kind") == "route" and e.get("out") == "local")
    cloud_routes = sum(1 for e in events if e.get("kind") == "route" and e.get("out") == "cloud")
    escalations = sum(1 for e in events if e.get("kind") == "escalate")
    return {"events": len(events), "tokens_saved": saved, "cache_hits": cache_hits,
            "local_routes": local_routes, "cloud_routes": cloud_routes,
            "escalations": escalations}


def render(project_root: str | Path = ".") -> str:
    """One line, safe to print in a status bar — never raises, empty-safe."""
    try:
        s = summarize(project_root)
    except Exception:
        return "🧦 botte"
    if not s["events"]:
        return "🧦 botte · no activity yet"
    parts = [f"🧦 {s['tokens_saved']:,} tok saved"]
    if s["cache_hits"]:
        parts.append(f"{s['cache_hits']} cache hits")
    if s["local_routes"] or s["cloud_routes"]:
        parts.append(f"{s['local_routes']}L/{s['cloud_routes']}C")
    if s["escalations"]:
        parts.append(f"{s['escalations']} escalated")
    return " · ".join(parts)
