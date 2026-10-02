"""Build a bounded read-only execution graph from existing Botte events."""

from collections import Counter
from pathlib import Path
from skills.events.events import read_events

SCHEMA = "botte.rsi-graph/v1"

def build_graph(project_root: str | Path = ".") -> dict:
    events = read_events(project_root)
    counts = Counter(str(e.get("kind", "unknown")) for e in events)
    nodes = [{"id": "event-kind:" + kind, "event_kind": kind, "observations": count}
             for kind, count in sorted(counts.items())]
    transitions = Counter()
    previous = None
    for event in events:
        current = str(event.get("kind", "unknown"))
        if previous is not None:
            transitions[(previous, current)] += 1
        previous = current
    edges = [{"source": "event-kind:" + source, "target": "event-kind:" + target,
              "relation": "observed_next", "observations": count}
             for (source, target), count in sorted(transitions.items())]
    return {
        "schema": SCHEMA, "mode": "observe", "read_only": True,
        "source": ".botte/events.jsonl", "event_count": len(events),
        "nodes": nodes, "edges": edges,
        "metrics": {"cost": None, "tokens": None, "compute": None, "energy": None},
        "limitations": [
            "edges represent temporal adjacency, not proven causality",
            "missing measurements remain unknown",
            "no route, tool, policy, or model is modified",
        ],
    }
