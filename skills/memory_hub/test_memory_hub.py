"""Tests for Memory Hub — schema, store, lifecycle, ACL, expiration, MCP dispatch.

Isolated via tmp_path; no global state.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from skills.memory_hub.schema import (
    MemoryEntry,
    MemoryStatus,
    MemoryVisibility,
    MemorySensitivity,
    AssetType,
    FULL_DDL,
)
from skills.memory_hub.store import MemoryStore, MemoryAccessError
from skills.memory_hub.mcp import dispatch, get_tools


# ══════════════════════════════════════════════════════════════════════
#  Schema tests
# ══════════════════════════════════════════════════════════════════════

class TestMemoryEntry:
    def test_default_status_is_proposal(self):
        e = MemoryEntry(key="k", value="v")
        assert e.status == MemoryStatus.PROPOSED.value

    def test_default_visibility_private(self):
        e = MemoryEntry(key="k", value="v")
        assert e.visibility == MemoryVisibility.PRIVATE.value

    def test_roundtrip_dict(self):
        e = MemoryEntry(key="k", value={"foo": [1, 2]}, source_ref="fable6:42",
                        tags=["urgent"], expires_at=1_800_000_000.0)
        d = e.to_dict()
        restored = MemoryEntry.from_dict(d)
        assert restored.key == "k"
        assert restored.value == {"foo": [1, 2]}
        assert restored.source_ref == "fable6:42"
        assert restored.tags == ["urgent"]
        assert restored.expires_at == 1_800_000_000.0

    def test_expires_none(self):
        e = MemoryEntry(key="k", value="v")
        assert e.expires_at is None
        restored = MemoryEntry.from_dict(e.to_dict())
        assert restored.expires_at is None


class TestMemoryStatusTransitions:
    def test_lifecycle_full(self):
        s = MemoryStatus.PROPOSED
        assert s.allowed_transitions() == [MemoryStatus.REVIEW_ACTIVE, MemoryStatus.EXPIRED]
        s = MemoryStatus.REVIEW_ACTIVE
        assert s.allowed_transitions() == [MemoryStatus.PROMOTED, MemoryStatus.OBSOLETED]

    def test_terminal_expired(self):
        assert MemoryStatus.EXPIRED.frozen()
        assert MemoryStatus.EXPIRED.allowed_transitions() == []


# ══════════════════════════════════════════════════════════════════════
#  Store tests
# ══════════════════════════════════════════════════════════════════════

@pytest.fixture
def store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(base_dir=tmp_path)


class TestMemoryStoreIsolation:
    def test_two_projects_isolated(self, store: MemoryStore):
        e1 = MemoryEntry(key="k", value=1, project_id="proj_a")
        e2 = MemoryEntry(key="k", value=2, project_id="proj_b")
        store.store(e1)
        store.store(e2)
        assert store.recall("proj_a", "k") == 1
        assert store.recall("proj_b", "k") == 2

    def test_list_projects(self, store: MemoryStore):
        store.store(MemoryEntry(key="a", value=1, project_id="p1"))
        store.store(MemoryEntry(key="b", value=2, project_id="p2"))
        assert sorted(store.list_projects()) == ["p1", "p2"]

    @pytest.mark.parametrize("project_id", ["../escape", "a/b", "a\\b", "", "x" * 129])
    def test_project_id_cannot_escape_storage(self, store: MemoryStore, project_id: str):
        with pytest.raises(ValueError):
            store.store(MemoryEntry(key="k", value=1, project_id=project_id))


class TestMemoryStoreCRUD:
    def test_store_and_recall(self, store: MemoryStore):
        store.store(MemoryEntry(key="greeting", value="hello", project_id="test"))
        assert store.recall("test", "greeting") == "hello"

    def test_recall_missing(self, store: MemoryStore):
        assert store.recall("test", "nosuch") is None

    def test_recall_with_value(self, store: MemoryStore):
        entry = MemoryEntry(key="complex", value={"a": 1, "b": [2]}, project_id="test")
        store.store(entry)
        got = store.get("test", "complex")
        assert got is not None
        assert got.value == {"a": 1, "b": [2]}

    def test_delete(self, store: MemoryStore):
        store.store(MemoryEntry(key="delme", value="x", project_id="test"))
        assert store.delete("test", "delme") is True
        assert store.recall("test", "delme") is None
        assert store.delete("test", "delme") is False

    def test_delete_rejects_non_owner(self, store: MemoryStore):
        store.store(MemoryEntry(key="private", value="x", project_id="test", agent_id="alice"))
        with pytest.raises(MemoryAccessError):
            store.delete("test", "private", actor_id="bob")
        assert store.delete("test", "private", actor_id="alice") is True

    def test_upsert_preserves_created_at_and_increments_version(self, store: MemoryStore):
        e1 = MemoryEntry(key="k", value="v1", project_id="p")
        store.store(e1)
        orig = store.get("p", "k")
        assert orig is not None
        created = orig.created_at
        assert orig.version == 1

        e2 = MemoryEntry(key="k", value="v2", project_id="p")
        store.store(e2)
        updated = store.get("p", "k")
        assert updated is not None
        assert updated.created_at == created
        assert updated.version == 2

    def test_upsert_rejects_non_owner(self, store: MemoryStore):
        store.store(MemoryEntry(key="k", value="alice", project_id="p", agent_id="alice"))
        with pytest.raises(MemoryAccessError):
            store.store(MemoryEntry(key="k", value="bob", project_id="p", agent_id="bob"))
        assert store.recall("p", "k", agent_id="alice") == "alice"


class TestMemoryStoreLifecycle:
    def test_proposed_default(self, store: MemoryStore):
        store.store(MemoryEntry(key="k", value="v", project_id="p"))
        entry = store.get("p", "k")
        assert entry is not None
        assert entry.status == MemoryStatus.PROPOSED.value

    def test_transition_proposal_to_active(self, store: MemoryStore):
        store.store(MemoryEntry(key="k", value="v", project_id="p", created_by="alice"))
        assert store.transition("p", "k", MemoryStatus.REVIEW_ACTIVE.value, actor_id="reviewer") is True
        entry = store.get("p", "k")
        assert entry is not None
        assert entry.status == MemoryStatus.REVIEW_ACTIVE.value
        assert entry.created_by == "alice"

    def test_transition_full_cycle(self, store: MemoryStore):
        store.store(MemoryEntry(key="k", value="v", project_id="p"))
        assert store.transition("p", "k", MemoryStatus.REVIEW_ACTIVE.value, actor_id="reviewer") is True
        assert store.transition("p", "k", MemoryStatus.PROMOTED.value, actor_id="reviewer") is True
        entry = store.get("p", "k")
        assert entry is not None
        assert entry.status == MemoryStatus.PROMOTED.value

    def test_illegal_transition_rejected(self, store: MemoryStore):
        store.store(MemoryEntry(key="k", value="v", project_id="p"))
        # proposed → promoted not allowed
        assert store.transition("p", "k", MemoryStatus.PROMOTED.value, actor_id="reviewer") is False

    def test_frozen_transition_rejected(self, store: MemoryStore):
        store.store(MemoryEntry(key="k", value="v", project_id="p"))
        assert store.transition("p", "k", MemoryStatus.EXPIRED.value, actor_id="reviewer") is True
        # expired is frozen
        assert store.transition("p", "k", MemoryStatus.PROMOTED.value, actor_id="reviewer") is False

    def test_transition_missing(self, store: MemoryStore):
        assert store.transition("p", "nonexistent", MemoryStatus.PROMOTED.value, actor_id="reviewer") is False

    def test_transition_requires_actor(self, store: MemoryStore):
        store.store(MemoryEntry(key="k", value="v", project_id="p"))
        assert store.transition("p", "k", MemoryStatus.REVIEW_ACTIVE.value) is False


class TestMemoryStoreExpiration:
    def test_prune_expired(self, store: MemoryStore):
        past = time.time() - 9999
        e1 = MemoryEntry(key="old", value="gone", project_id="p", expires_at=past)
        e2 = MemoryEntry(key="fresh", value="keep", project_id="p")  # no expiry
        store.store(e1)
        store.store(e2)
        pruned = store.prune_expired("p")
        assert pruned == 1
        assert store.recall("p", "old") is None
        assert store.recall("p", "fresh") is not None


class TestMemoryStoreSearch:
    def test_search_by_query(self, store: MemoryStore):
        store.store(MemoryEntry(key="design:auth", value="OAuth2", project_id="p"))
        store.store(MemoryEntry(key="design:cache", value="Redis", project_id="p"))
        results = store.search("p", query="auth")
        assert len(results) == 1
        assert results[0].key == "design:auth"

    def test_search_by_asset_type(self, store: MemoryStore):
        store.store(MemoryEntry(key="sk", value="skill", asset_type="skill", project_id="p"))
        store.store(MemoryEntry(key="wk", value="wiki", asset_type="wiki", project_id="p"))
        results = store.search("p", asset_type="skill")
        assert len(results) == 1
        assert results[0].key == "sk"


class TestMemoryStoreACL:
    def test_private_visible_only_to_owner(self, store: MemoryStore):
        store.store(MemoryEntry(key="secret", value="hidden", project_id="p",
                                agent_id="alice", visibility="private"))
        # bob cannot see it
        assert store.get("p", "secret", agent_id="bob") is None
        # alice can
        assert store.get("p", "secret", agent_id="alice") is not None

    def test_project_visible_to_any_agent(self, store: MemoryStore):
        store.store(MemoryEntry(key="shared", value="ok", project_id="p",
                                agent_id="alice", visibility="project"))
        assert store.get("p", "shared", agent_id="bob") is not None

    def test_search_respects_acl(self, store: MemoryStore):
        store.store(MemoryEntry(key="alice_priv", value="a", project_id="p",
                                agent_id="alice", visibility="private"))
        store.store(MemoryEntry(key="shared_k", value="s", project_id="p",
                                agent_id="alice", visibility="project"))
        results = store.search("p", agent_id="bob")
        keys = {r.key for r in results}
        assert "shared_k" in keys
        assert "alice_priv" not in keys


# ══════════════════════════════════════════════════════════════════════
#  Context bundle tests
# ══════════════════════════════════════════════════════════════════════

class TestContextBundle:
    def test_bundle_respects_acl(self, store: MemoryStore):
        store.store(MemoryEntry(key="pub", value="public", project_id="p",
                                status="promoted", visibility="project"))
        store.store(MemoryEntry(key="priv", value="private", project_id="p",
                                agent_id="alice", status="promoted", visibility="private"))
        bundle = store.context_bundle("p", agent_id="bob")
        keys = {b["key"] for b in bundle}
        assert "pub" in keys
        assert "priv" not in keys

    def test_bundle_includes_own_private(self, store: MemoryStore):
        store.store(MemoryEntry(key="pub", value="public", project_id="p",
                                status="promoted", visibility="project"))
        store.store(MemoryEntry(key="mine", value="private", project_id="p",
                                agent_id="alice", status="promoted", visibility="private"))
        bundle = store.context_bundle("p", agent_id="alice")
        keys = {b["key"] for b in bundle}
        assert "pub" in keys
        assert "mine" in keys

    def test_bundle_excludes_unreviewed_private_proposal(self, store: MemoryStore):
        store.store(MemoryEntry(key="draft", value="private", project_id="p",
                                agent_id="alice", status="proposal", visibility="private"))
        assert store.context_bundle("p", agent_id="alice") == []


# ══════════════════════════════════════════════════════════════════════
#  MCP dispatch tests
# ══════════════════════════════════════════════════════════════════════

class TestMCPDispatch:
    def test_tools_defined(self):
        tools = get_tools()
        names = {t["name"] for t in tools}
        assert "search_hub" in names
        assert "context_bundle" in names
        assert "propose_memory" in names
        assert "promote_memory" in names
        assert "forget_memory" in names

    def test_propose_returns_status(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("BOTTE_MEMORY_HUB_DIR", str(tmp_path))
        out = dispatch("propose_memory", {
            "project_id": "test",
            "key": "mcp:prop",
            "value": "mcp value",
            "agent_id": "alice",
        })
        assert out["key"] == "mcp:prop"
        assert out["status"] == MemoryStatus.PROPOSED.value

    def test_promote_via_dispatch(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("BOTTE_MEMORY_HUB_DIR", str(tmp_path))
        dispatch("propose_memory", {
            "project_id": "test", "key": "mcp:prom", "value": "x", "agent_id": "alice",
        })
        out = dispatch("promote_memory", {
            "project_id": "test", "key": "mcp:prom",
            "new_status": MemoryStatus.REVIEW_ACTIVE.value, "actor_id": "reviewer",
        })
        assert out["success"] is True

    def test_forget_via_dispatch(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("BOTTE_MEMORY_HUB_DIR", str(tmp_path))
        dispatch("propose_memory", {
            "project_id": "test", "key": "mcp:forget", "value": "x", "agent_id": "alice",
        })
        out = dispatch("forget_memory", {
            "project_id": "test", "key": "mcp:forget", "actor_id": "alice",
        })
        assert out["deleted"] is True

    def test_forget_requires_actor(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("BOTTE_MEMORY_HUB_DIR", str(tmp_path))
        dispatch("propose_memory", {
            "project_id": "test", "key": "mcp:no-actor", "value": "x", "agent_id": "alice",
        })
        out = dispatch("forget_memory", {"project_id": "test", "key": "mcp:no-actor"})
        assert out["deleted"] is False

    def test_dispatch_unknown_tool(self):
        out = dispatch("nonexistent", {})
        assert "error" in out


# ══════════════════════════════════════════════════════════════════════
#  Stats
# ══════════════════════════════════════════════════════════════════════

class TestStats:
    def test_stats_counts(self, store: MemoryStore):
        store.store(MemoryEntry(key="a", value=1, project_id="p", asset_type="fact"))
        store.store(MemoryEntry(key="b", value=2, project_id="p", asset_type="skill"))
        store.store(MemoryEntry(key="c", value=3, project_id="p", asset_type="skill",
                                status=MemoryStatus.PROMOTED.value))
        s = store.stats("p")
        assert s["total"] == 3
        assert s["by_asset"]["fact"] == 1
        assert s["by_asset"]["skill"] == 2
        assert s["by_status"]["proposal"] == 2
        assert s["by_status"]["promoted"] == 1
