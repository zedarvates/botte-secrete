"""Dashboard — one HTML view of cost, savings, trends and fixes.

Assembles the live numbers from the system's own measurement modules into a
single self-contained HTML page (saved, timestamped) you can open any time:
routing savings (control_loop), metric trends, current metrics, and the cost of
outstanding fixes. Pure stdlib (renders via skills.report).
"""

from __future__ import annotations

from pathlib import Path


def collect(project: str | Path) -> dict:
    project = Path(project).resolve()
    out: dict = {"project": str(project)}

    try:
        from skills.control_loop.control_loop import analyze
        out["routing_savings"] = analyze()
    except Exception as e:
        out["routing_savings"] = {"error": str(e)}

    try:
        from skills.trends import show
        out["trends"] = show(project)
    except Exception as e:
        out["trends"] = {"error": str(e)}

    try:
        from skills.metrics import collect as mcollect
        m = mcollect(project)
        out["metrics"] = {"loc_total": m.loc_total, "files": m.files_total,
                          "duplicate_groups": m.duplicate_groups,
                          "directive_score": m.directive_score, "cost": m.cost}
    except Exception as e:
        out["metrics"] = {"error": str(e)}

    try:
        from skills.fix import find_fixes
        f = find_fixes(project)
        out["outstanding_fixes"] = {"total": f["total_fixes"], "by_kind": f["by_kind"],
                                    "cost_to_apply": f["totals"]}
    except Exception as e:
        out["outstanding_fixes"] = {"error": str(e)}

    try:
        from skills.events.events import read_events
        events = read_events(project)
        loop_events = [event for event in events if str(event.get("kind", "")).startswith("loop_")]
        out["loops"] = {
            "events": len(loop_events),
            "decisions": sum(event.get("kind") == "loop_decision" for event in loop_events),
            "stops": sum(event.get("kind") == "loop_stop" for event in loop_events),
            "cache_hits": sum(bool(event.get("cache_hit")) for event in loop_events),
            "cloud_tokens": sum(int(event.get("cloud_tokens", 0)) for event in loop_events),
            "tokens_used": sum(int(event.get("tokens_used", 0)) for event in loop_events),
            "iterations_avoided": sum(int(event.get("iterations_avoided", 0)) for event in loop_events),
            "agents_skipped": sum(int(event.get("agents_skipped", 0)) for event in loop_events),
            "repetitions_blocked": sum(event.get("reason") == "repeated_failure" for event in loop_events),
            "escalations": sum(event.get("action") == "escalate" for event in loop_events),
        }
    except Exception as e:
        out["loops"] = {"error": str(e)}

    return out


def generate(project: str | Path, *, fmt: str = "html") -> list[str]:
    """Build the dashboard and save it (timestamped) under .botte/reports/."""
    data = collect(project)
    from skills.report import save
    return save("dashboard", data, fmt=fmt,
                out_dir=Path(data["project"]) / ".botte" / "reports",
                title=f"Botte dashboard — {data['project']}")
