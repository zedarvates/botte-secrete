"""Build a bounded read-only execution graph from existing Botte events."""

from collections import Counter
import json
from pathlib import Path

SCHEMA = "botte.rsi-graph/v1"
MAX_SOURCE_BYTES = 5 * 1024 * 1024


def _read_observations(project_root):
    try:
        path = Path(project_root).resolve() / ".botte" / "events.jsonl"
        with path.open("rb") as stream:
            raw = stream.read(MAX_SOURCE_BYTES + 1)
    except FileNotFoundError:
        return [], "missing", 0
    except (OSError, RuntimeError):
        return [], "unavailable", 0
    if len(raw) > MAX_SOURCE_BYTES:
        return [], "too_large", 0
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return [], "invalid", 0
    events = []
    rejected = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except (ValueError, RecursionError):
            rejected += 1
            continue
        if not isinstance(event, dict):
            rejected += 1
            continue
        events.append(event)
    return events, "partial" if rejected else "ok", rejected


def _identity(event):
    kind = str(event.get("kind", "unknown"))
    producer = event.get("producer")
    component_kind = event.get("component_kind")
    if producer:
        node_id = "producer:" + str(producer) + ":" + str(component_kind or "unknown") + ":" + kind
        return node_id, kind, str(producer), str(component_kind) if component_kind else None
    return "event-kind:" + kind, kind, None, None


def build_graph(project_root: str | Path = ".") -> dict:
    events, source_status, rejected = _read_observations(project_root)
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
        "source_status": source_status, "rejected_records": rejected,
        "source_max_bytes": MAX_SOURCE_BYTES,
        "nodes": nodes, "edges": edges,
        "metrics": {"cost": None, "tokens": None, "compute": None, "energy": None},
        "limitations": [
            "edges represent temporal adjacency, not proven causality",
            "missing measurements remain unknown",
            "legacy events without explicit producer keep unknown provenance",
            "no route, tool, policy, or model is modified",
        ] + ([] if source_status == "ok" else [
            "source_status=" + source_status + "; input is not a verified complete history",
        ]),
    }
