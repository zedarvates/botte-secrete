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
