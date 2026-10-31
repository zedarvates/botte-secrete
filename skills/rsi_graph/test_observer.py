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
    assert nodes["route"]["id"] == 'producer:["skills.auto_router","router","route"]'
    assert nodes["legacy"]["provenance"] == "unknown"
    assert nodes["legacy"]["id"] == "event-kind:legacy"
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
    from unittest.mock import patch
    with patch("skills.rsi_graph.observer.os.open", side_effect=PermissionError("synthetic input")):
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
    from unittest.mock import patch
    from skills.rsi_graph import observer
    path = tmp_path / ".botte" / "events.jsonl"
    path.parent.mkdir()
    path.write_bytes(b"x" * 33)
    requested = []
    class TrackingReader:
        def __init__(self, stream):
            self.stream = stream
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return self.stream.__exit__(*args)
        def fileno(self):
            return self.stream.fileno()
        def read(self, size=-1):
            requested.append(size)
            return self.stream.read(size)
    real_fdopen = observer.os.fdopen
    with patch.object(observer, "MAX_SOURCE_BYTES", 32), patch.object(
        observer.os, "fdopen", side_effect=lambda *a, **kw: TrackingReader(real_fdopen(*a, **kw))
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


def test_same_event_kind_from_two_producers_stays_separate(tmp_path):
    import json
    botte = tmp_path / ".botte"
    botte.mkdir()
    records = [
        {"kind": "route", "producer": "a", "component_kind": "router"},
        {"kind": "route", "producer": "b", "component_kind": "router"},
    ]
    payload = chr(10).join(json.dumps(record) for record in records) + chr(10)
    (botte / "events.jsonl").write_text(payload, encoding="utf-8")
    graph = build_graph(tmp_path)
    ids = {node["id"] for node in graph["nodes"]}
    assert ids == {'producer:["a","router","route"]', 'producer:["b","router","route"]'}


def test_observer_does_not_apply_event_instructions(tmp_path):
    from pathlib import Path
    from unittest.mock import patch
    path = tmp_path / ".botte" / "events.jsonl"
    path.parent.mkdir()
    original = '{"kind":"promote","action":"rewrite_policy","target":"policy.md"}\n'
    path.write_text(original, encoding="utf-8")
    policy = tmp_path / "policy.md"
    policy.write_text("Owner approval required.\n", encoding="utf-8")
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    real_open = Path.open
    def read_only_open(self, mode="r", *args, **kwargs):
        assert mode == "rb", "observer attempted a write or another input mode"
        return real_open(self, mode, *args, **kwargs)
    with patch.object(Path, "open", read_only_open):
        graph = build_graph(tmp_path)
    after = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert before == after
    assert graph["event_count"] == 1 and graph["read_only"] is True


def test_identity_encoding_separates_delimiters_and_missing_components(tmp_path):
    import json
    path = tmp_path / ".botte" / "events.jsonl"
    path.parent.mkdir()
    rows = [
        {"kind": "route", "producer": "a:b", "component_kind": "c"},
        {"kind": "route", "producer": "a", "component_kind": "b:c"},
        {"kind": "route", "producer": "a"},
        {"kind": "route", "producer": "a", "component_kind": "unknown"},
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    graph = build_graph(tmp_path)
    assert graph["event_count"] == 4 and len(graph["nodes"]) == 4
    assert all(node["observations"] == 1 for node in graph["nodes"])
    assert len(graph["edges"]) == 3


def test_invalid_identity_and_json_never_become_trusted_provenance(tmp_path):
    import json
    path = tmp_path / ".botte" / "events.jsonl"
    path.parent.mkdir()
    rows = [{}, {"kind": ""}, {"kind": 2}, {"kind": "\ud800"},
            {"kind": "route", "producer": []}, {"kind": "route", "producer": ""},
            {"kind": "route", "producer": "a", "component_kind": {}}]
    original = "".join(json.dumps(row) + "\n" for row in rows)
    original += '{"kind":"a","kind":"b"}\n{"kind":"route","value":NaN}\n'
    path.write_text(original, encoding="utf-8")
    graph = build_graph(tmp_path)
    assert graph["source_status"] == "partial" and graph["rejected_records"] == 9
    assert graph["event_count"] == 0 and graph["nodes"] == []
    assert path.read_text(encoding="utf-8") == original


def test_rejected_record_breaks_adjacency(tmp_path):
    path = tmp_path / ".botte" / "events.jsonl"
    path.parent.mkdir()
    path.write_text('{"kind":"route"}\ninvalid\n{"kind":"verify"}\n', encoding="utf-8")
    graph = build_graph(tmp_path)
    assert graph["event_count"] == 2 and graph["source_status"] == "partial"
    assert graph["edges"] == []


def test_special_file_does_not_block_the_observer(tmp_path):
    import os
    import subprocess
    import sys
    from unittest.mock import patch
    from skills.rsi_graph import observer
    if not hasattr(os, "mkfifo"):
        # The descriptor guard is platform independent; exercise it without a FIFO.
        import stat
        from types import SimpleNamespace
        path = tmp_path / ".botte" / "events.jsonl"
        path.parent.mkdir()
        path.write_text("", encoding="utf-8")
        with patch.object(observer.os, "fstat", return_value=SimpleNamespace(st_mode=stat.S_IFCHR)):
            assert build_graph(tmp_path)["source_status"] == "unavailable"
        return
    path = tmp_path / ".botte" / "events.jsonl"
    path.parent.mkdir()
    os.mkfifo(path)
    child = subprocess.run(
        [sys.executable, "-m", "skills.rsi_graph.cli", "observe", str(tmp_path), "--json"],
        capture_output=True, text=True, encoding="utf-8", timeout=10,
    )
    assert child.returncode == 2 and '"source_status": "unavailable"' in child.stdout


def test_symlinked_log_or_directory_is_not_followed(tmp_path):
    from unittest.mock import patch
    from pathlib import Path
    with patch.object(Path, "is_symlink", return_value=True):
        assert build_graph(tmp_path)["source_status"] == "unavailable"
