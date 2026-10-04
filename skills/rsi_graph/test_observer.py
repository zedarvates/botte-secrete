from skills.rsi_graph.observer import build_graph

def test_empty_graph_does_not_invent_metrics(tmp_path):
    graph = build_graph(tmp_path)
    assert graph["schema"] == "botte.rsi-graph/v1"
    assert graph["read_only"] is True
    assert graph["event_count"] == 0
    assert graph["metrics"]["cost"] is None
    assert graph["metrics"]["tokens"] is None

def test_edges_are_observed_adjacency_not_causality(tmp_path):
    botte = tmp_path / ".botte"
    botte.mkdir()
    path = botte / "events.jsonl"
    original = '{"ts":1,"kind":"route"}\n{"ts":2,"kind":"escalate"}\n'
    path.write_text(original, encoding="utf-8")
    graph = build_graph(tmp_path)
    assert graph["edges"] == [{
        "source": "event-kind:route", "target": "event-kind:escalate",
        "relation": "observed_next", "observations": 1,
    }]
    assert path.read_text(encoding="utf-8") == original
    assert any("not proven causality" in x for x in graph["limitations"])

def test_provenance_is_only_claimed_when_event_records_it(tmp_path):
    botte = tmp_path / ".botte"
    botte.mkdir()
    (botte / "events.jsonl").write_text(
        '{"ts":1,"kind":"route","producer":"skills.auto_router","component_kind":"router"}\n'
        '{"ts":2,"kind":"legacy"}\n',
        encoding="utf-8",
    )
    graph = build_graph(tmp_path)
    nodes = {node["event_kind"]: node for node in graph["nodes"]}
    assert nodes["route"]["producer"] == "skills.auto_router"
    assert nodes["route"]["component_kind"] == "router"
    assert nodes["route"]["provenance"] == "explicit_event_fields"
    assert nodes["legacy"]["provenance"] == "unknown"
    assert "producer" not in nodes["legacy"]

def test_non_object_and_malformed_records_are_counted(tmp_path):
    import json
    botte = tmp_path / ".botte"
    botte.mkdir()
    path = botte / "events.jsonl"
    invalid = [None, [], 1, "event", True]
    original = '{"kind":"route","producer":"skills.auto_router","component_kind":"router"}\n'
    original += "".join(json.dumps(value) + "\n" for value in invalid)
    original += '{"broken":\n'
    path.write_text(original, encoding="utf-8")
    graph = build_graph(tmp_path)
    assert graph["event_count"] == 1
    assert graph["source_status"] == "partial"
    assert graph["rejected_records"] == 6
    assert graph["nodes"][0]["producer"] == "skills.auto_router"
    assert graph["nodes"][0]["provenance"] == "explicit_event_fields"
    assert path.read_text(encoding="utf-8") == original


def test_invalid_utf8_has_an_explicit_source_status(tmp_path):
    path = tmp_path / ".botte" / "events.jsonl"
    path.parent.mkdir()
    original = b"\xff\xfe\n"
    path.write_bytes(original)
    graph = build_graph(tmp_path)
    assert graph["source_status"] == "invalid"
    assert graph["event_count"] == 0
    assert all(value is None for value in graph["metrics"].values())
    assert path.read_bytes() == original


def test_unavailable_source_does_not_claim_empty_success(tmp_path):
    from pathlib import Path
    from unittest.mock import patch
    with patch.object(Path, "open", side_effect=PermissionError("synthetic input")):
        graph = build_graph(tmp_path)
    assert graph["source_status"] == "unavailable"
    assert any("not a verified complete history" in note for note in graph["limitations"])


def test_missing_and_empty_readable_histories_are_distinguished(tmp_path):
    graph = build_graph(tmp_path)
    assert graph["source_status"] == "missing"
    assert not (tmp_path / ".botte").exists()
    path = tmp_path / ".botte" / "events.jsonl"
    path.parent.mkdir()
    path.write_text("", encoding="utf-8")
    graph = build_graph(tmp_path)
    assert graph["source_status"] == "ok" and graph["event_count"] == 0


def test_oversized_source_uses_a_bounded_sentinel_read(tmp_path):
    import io
    from pathlib import Path
    from unittest.mock import patch
    from skills.rsi_graph import observer
    requested = []
    class TrackingReader(io.BytesIO):
        def read(self, size=-1):
            requested.append(size)
            return super().read(size)
    with patch.object(observer, "MAX_SOURCE_BYTES", 32), patch.object(
        Path, "open", return_value=TrackingReader(b"x" * 33)
    ):
        graph = build_graph(tmp_path)
    assert requested == [33]
    assert graph["source_status"] == "too_large"
    assert graph["event_count"] == 0 and graph["nodes"] == [] and graph["edges"] == []


def test_source_at_the_exact_byte_limit_is_accepted(tmp_path):
    from unittest.mock import patch
    from skills.rsi_graph import observer
    path = tmp_path / ".botte" / "events.jsonl"
    path.parent.mkdir()
    original = '{"kind":"route"}\n'
    path.write_text(original, encoding="utf-8")
    with patch.object(observer, "MAX_SOURCE_BYTES", len(original.encode("utf-8"))):
        graph = build_graph(tmp_path)
    assert graph["source_status"] == "ok" and graph["event_count"] == 1
    assert path.read_text(encoding="utf-8") == original
