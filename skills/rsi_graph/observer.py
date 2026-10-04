"""Build a bounded read-only execution graph from existing Botte events."""

from collections import Counter
from pathlib import Path
from skills.events.events import read_events

SCHEMA = "botte.rsi-graph/v1"

def _identity(event: dict) -> tuple[str, str, str | None, str | None]:
    kind = str(event.get("kind", "unknown"))
    producer = event.get("producer")
    component_kind = event.get("component_kind")
    if producer:
        node_id = "producer:" + str(producer) + ":" + str(component_kind or "unknown") + ":" + kind
        return node_id, kind, str(producer), str(component_kind) if component_kind else None
    return "event-kind:" + kind, kind, None, None

def build_graph(project_root: str | Path = ".") -> dict:
    events = read_events(project_root)
    identities = [_identity(event) for event in events]
    counts = Counter(identity[0] for identity in identities)
    metadata = {identity[0]: identity[1:] for identity in identities}
    nodes = []
    for node_id, count in sorted(counts.items()):
        kind, producer, component_kind = metadata[node_id]
        node = {"id": node_id, "event_kind": kind, "observations": count}
        if producer:
            node.update({"producer": producer, "component_kind": component_kind,
                         "provenance": "explicit_event_fields"})
        else:
            node["provenance"] = "unknown"
        nodes.append(node)
    transitions = Counter()
    previous = None
    for identity in identities:
        current = identity[0]
        if previous is not None:
            transitions[(previous, current)] += 1
        previous = current
    edges = [{"source": source, "target": target, "relation": "observed_next",
              "observations": count}
             for (source, target), count in sorted(transitions.items())]
    return {
        "schema": SCHEMA, "mode": "observe", "read_only": True,
        "source": ".botte/events.jsonl", "event_count": len(events),
        "nodes": nodes, "edges": edges,
        "metrics": {"cost": None, "tokens": None, "compute": None, "energy": None},
        "limitations": [
            "edges represent temporal adjacency, not proven causality",
            "missing measurements remain unknown",
            "legacy events without explicit producer keep unknown provenance",
            "no route, tool, policy, or model is modified",
        ],
    }
