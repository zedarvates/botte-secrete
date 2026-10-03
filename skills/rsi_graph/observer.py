"""Build a bounded read-only execution graph from existing Botte events."""

from collections import Counter
from pathlib import Path
from skills.events.events import read_events

SCHEMA = "botte.rsi-graph/v1"

def build_graph(project_root: str | Path = ".") -> dict:
    events = read_events(project_root)
    counts = Counter(str(e.get("kind", "unknown")) for e in events)
    provenance = {}
    for event in events:
        kind = str(event.get("kind", "unknown"))
        producer = event.get("producer")
        component_kind = event.get("component_kind")
        if producer:
            provenance[kind] = {"producer": str(producer), "component_kind": component_kind}
    nodes = []
    for kind, count in sorted(counts.items()):
        node = {"id": "event-kind:" + kind, "event_kind": kind, "observations": count}
        if kind in provenance:
            node.update(provenance[kind])
            node["provenance"] = "explicit_event_fields"
        else:
            node["provenance"] = "unknown"
        nodes.append(node)
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
