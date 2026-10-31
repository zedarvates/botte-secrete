"""Build a bounded read-only execution graph from existing Botte events."""

from collections import Counter
import json
import os
from pathlib import Path
import stat

SCHEMA = "botte.rsi-graph/v1"
MAX_SOURCE_BYTES = 5 * 1024 * 1024


def _read_observations(project_root):
    try:
        path = Path(project_root).resolve() / ".botte" / "events.jsonl"
        if path.parent.is_symlink() or path.is_symlink():
            return [], "unavailable", 0
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                return [], "unavailable", 0
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
            event = json.loads(line, object_pairs_hook=_unique_fields, parse_constant=_invalid_constant)
        except (ValueError, RecursionError):
            rejected += 1
            events.append(None)
            continue
        if not _valid_event(event):
            rejected += 1
            events.append(None)
            continue
        events.append(event)
    return events, "partial" if rejected else "ok", rejected


def _invalid_constant(value):
    raise ValueError("nonfinite JSON constant")


def _unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _valid_event(event):
    if not isinstance(event, dict):
        return False
    for field in ("kind", "producer", "component_kind"):
        value = event.get(field)
        if value is None and field != "kind":
            continue
        if not isinstance(value, str) or not value.strip():
            return False
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            return False
    return True


def _identity(event):
    kind = event["kind"]
    producer = event.get("producer")
    component_kind = event.get("component_kind")
    if producer:
        node_id = "producer:" + json.dumps([producer, component_kind, kind], ensure_ascii=True, separators=(",", ":"))
        return node_id, kind, producer, component_kind
    return "event-kind:" + kind, kind, None, None


def build_graph(project_root: str | Path = ".") -> dict:
    events, source_status, rejected = _read_observations(project_root)
    identities = [_identity(event) if event is not None else None for event in events]
    counts = Counter(identity[0] for identity in identities if identity is not None)
    metadata = {identity[0]: identity[1:] for identity in identities if identity is not None}
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
        if identity is None:
            previous = None
            continue
        current = identity[0]
        if previous is not None:
            transitions[(previous, current)] += 1
        previous = current
    edges = [{"source": source, "target": target, "relation": "observed_next",
              "observations": count}
             for (source, target), count in sorted(transitions.items())]
    return {
        "schema": SCHEMA, "mode": "observe", "read_only": True,
        "source": ".botte/events.jsonl", "event_count": sum(counts.values()),
        "source_status": source_status, "rejected_records": rejected,
        "source_max_bytes": MAX_SOURCE_BYTES,
        "nodes": nodes, "edges": edges,
        "metrics": {"cost": None, "tokens": None, "compute": None, "energy": None},
        "limitations": [
            "edges represent temporal adjacency, not proven causality",
            "missing measurements remain unknown",
            "legacy events without explicit producer keep unknown provenance",
            "no route, tool, policy, or model is modified",
            "rejected records break adjacency chains",
            "input is a bounded regular-file read, not an OS sandbox or a quiescent log snapshot",
        ] + ([] if source_status == "ok" else [
            "source_status=" + source_status + "; input is not a verified complete history",
        ]),
    }
