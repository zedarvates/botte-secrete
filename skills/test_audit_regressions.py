"""Regression coverage for correctness defects found by the repository audit."""

import json

from skills.agent_compression import cli as agent_compression
from skills.cache import ProjectCache
from skills.context_windows.cli import WindowManager
from skills.dag_optimizer.cli import DAGGraph
from skills.events import events
from skills.response_cache import ResponseCache
from skills.atomic_json import write_json
from skills.token_compressor.cli import TokenCompressor


def test_agent_compression_preserves_whitespace_and_unicode(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_compression, "DICT_STORE", tmp_path / "dict.json")
    compressor = agent_compression.A2ACCompressor()
    original = "alpha  beta\n\tclé: valeur\n"

    encoded = compressor.dict.encode(original)

    # Learn first, as the public compress path does, then verify exact roundtrip.
    compressor.dict.learn(original)
    encoded = compressor.dict.encode(original)
    assert compressor.dict.decode(encoded) == original

    updated = "alpha  beta\n\tclé: nouvelle valeur\n"
    delta = compressor.delta(original, updated)
    assert compressor.apply_delta(original, delta) == updated


def test_token_compressor_roundtrip_is_self_contained():
    original = '{"checksum":"deadbeef01234567","lines":"a  b\\nç"}'
    payload = TokenCompressor().compress(original)

    assert payload.startswith("TC1:")
    assert TokenCompressor().expand(payload) == original


def test_dag_stats_does_not_mutate_graph():
    dag = DAGGraph.__new__(DAGGraph)
    dag.nodes = {"used": {"name": "used"}, "orphan": {"name": "orphan"}}
    dag.edges = []
    dag._memo = {}
    before = (dict(dag.nodes), list(dag.edges))

    dag.stats()

    assert dag.nodes == before[0]
    assert dag.edges == before[1]


def test_project_cache_invalidates_after_source_change(tmp_path):
    source = tmp_path / "source.py"
    source.write_text("one", encoding="utf-8")
    cache = ProjectCache(str(tmp_path))
    cache.set("scan-result", {"files": 1})
    assert cache.get("scan-result") is not None

    source.write_text("two-two", encoding="utf-8")

    assert cache.get("scan-result") is None


def test_event_follower_recovers_after_rotation(monkeypatch):
    snapshots = iter([
        [{"id": 1}, {"id": 2}, {"id": 3}],
        [{"id": 4}],
    ])
    monkeypatch.setattr(events, "read_events", lambda _root: next(snapshots))

    follower = events.follow_events(".", poll_interval=0)

    assert next(follower) == {"id": 4}


def test_response_cache_separates_model_and_system_context(tmp_path):
    cache = ResponseCache(str(tmp_path))
    cache.set("same prompt", "answer-a", model="model-a", context="system-a",
              tokens_used=42)

    assert cache.get("same prompt", model="model-a", context="system-a").response == "answer-a"
    assert cache.get("same prompt", model="model-b", context="system-a") is None
    assert cache.get("same prompt", model="model-a", context="system-b") is None
    restored = ResponseCache(str(tmp_path))
    assert restored.report()["hits_exact"] == 1
    assert restored.report()["tokens_saved_total"] == 42


def test_context_windows_persist_and_merge(tmp_path):
    store = tmp_path / "windows.json"
    first = WindowManager(store_path=store)
    first.create_window("active", "current code")
    first.create_window("reference", "API contract", "reference")

    restored = WindowManager(store_path=store)

    assert restored.merge(["active", "reference"]) == "current code\n\nAPI contract"
    assert restored.total_tokens() == first.total_tokens()


def test_atomic_json_replaces_document(tmp_path):
    target = tmp_path / "state.json"
    write_json(target, {"version": 1})
    write_json(target, {"version": 2, "unicode": "clé"})

    assert json.loads(target.read_text(encoding="utf-8")) == {
        "version": 2, "unicode": "clé",
    }
    assert list(tmp_path.glob("*.tmp")) == []
