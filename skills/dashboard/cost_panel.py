#!/usr/bin/env python3
"""Dashboard TUI cost panel — cumulative cloud cost display.

Add-on for dashboard --tui mode. Shows $ spent this session.
"""

from __future__ import annotations


def cost_panel(events: list[dict]) -> str:
    """Build a cost summary panel from events."""
    cloud_events = [e for e in events if e.get("mode") == "cloud" or e.get("escalated")]
    total_cloud = len(cloud_events)
    total_events = len(events)
    local_pct = round(100 * (total_events - total_cloud) / max(total_events, 1), 1)

    # Estimate cost (rough: $0.002 per standard cloud call)
    est_cost = total_cloud * 0.002

    lines = [
        "┌─ 💰 Cost Panel ─────────────────────┐",
        f"│ Cloud calls:   {total_cloud:>4}                 │",
        f"│ Local calls:   {total_events - total_cloud:>4}  ({local_pct}%)        │",
        f"│ Est. cost:    ${est_cost:.4f}               │",
        "└──────────────────────────────────────┘",
    ]
    return "\n".join(lines)
