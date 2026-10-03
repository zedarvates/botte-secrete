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
        '{"ts":1,"kind":"route","producer":"skills.auto_router","component_kind":"router"}\\n'
        '{"ts":2,"kind":"legacy"}\\n',
        encoding="utf-8",
    )
    graph = build_graph(tmp_path)
    nodes = {node["event_kind"]: node for node in graph["nodes"]}
    assert nodes["route"]["producer"] == "skills.auto_router"
    assert nodes["route"]["component_kind"] == "router"
    assert nodes["route"]["provenance"] == "explicit_event_fields"
    assert nodes["legacy"]["provenance"] == "unknown"
    assert "producer" not in nodes["legacy"]
