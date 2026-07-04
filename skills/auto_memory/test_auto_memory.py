"""Tests for auto_memory skill."""
import json
import tempfile
from pathlib import Path

from skills.auto_memory.memory_bank import MemoryBank, MemoryEntry
from skills.auto_memory.compressor import compress_memories, extract_patterns, bottleneck_compress
from skills.auto_memory.hook import init_memory, store_memory, recall_memory, memory_stats


class TestMemoryEntry:
    def test_to_dict_roundtrip(self):
        entry = MemoryEntry(key="test.key", value={"foo": "bar"}, category="fact", confidence=0.9)
        d = entry.to_dict()
        restored = MemoryEntry.from_dict(d)
        assert restored.key == entry.key
        assert restored.value == entry.value


class TestMemoryBank:
    def test_store_and_recall(self, tmp_path):
        bank = MemoryBank(base_dir=tmp_path)
        bank.store("user_pref.format", "concise", category="user_pref", confidence=0.95)
        assert bank.recall("user_pref.format") == "concise"
        assert bank.recall("nonexistent", "default") == "default"

    def test_search(self, tmp_path):
        bank = MemoryBank(base_dir=tmp_path)
        bank.store("pref.lang", "fr", category="user_pref", confidence=0.9)
        bank.store("pref.style", "direct", category="user_pref", confidence=0.9)
        bank.store("fact.version", "1.0", category="fact", confidence=0.8)
        results = bank.search(category="user_pref")
        assert len(results) == 2
        keys = [r.key for r in results]
        assert "pref.lang" in keys

    def test_forget(self, tmp_path):
        bank = MemoryBank(base_dir=tmp_path)
        bank.store("temp", "value", confidence=0.5)
        bank.forget("temp")
        assert bank.recall("temp") is None

    def test_stats(self, tmp_path):
        bank = MemoryBank(base_dir=tmp_path)
        bank.store("a", 1)
        bank.store("b", 2, category="fact")
        s = bank.stats()
        assert s["total_entries"] == 2
        assert "user_pref" in s["by_category"] or "fact" in s["by_category"]


class TestCompressor:
    def test_compress_memories(self, tmp_path):
        bank = MemoryBank(base_dir=tmp_path)
        bank.store("user_pref_1", "value1")
        bank.store("user_pref_2", "value2")  # Will merge with user_pref_1
        merged = compress_memories(bank)
        assert merged >= 1  # at least one merge

    def test_extract_patterns(self):
        entries = [
            MemoryEntry(key="log.1", value='{"error": "fail", "count": 1}', category="log", confidence=0.9),
            MemoryEntry(key="log.2", value='{"error": "fail", "count": 2}', category="log", confidence=0.9),
        ]
        patterns = extract_patterns(entries)
        assert any(p["type"] == "json_keys" for p in patterns)

    def test_bottleneck_compress(self, tmp_path):
        bank = MemoryBank(base_dir=tmp_path)
        for i in range(10):
            bank.store(f"item_{i}", i, confidence=0.5 if i < 5 else 1.0)
        removed = bottleneck_compress(bank, keep_pct=0.3)
        assert removed >= 5  # removed low-confidence entries


class TestHook:
    def test_init_and_stats(self, tmp_path):
        bank = init_memory()
        bank.base = tmp_path  # override for test isolation
        store_memory("test.key", "test_value", category="user_pref")
        assert recall_memory("test.key") == "test_value"
        stats = memory_stats()
        assert stats["total_entries"] >= 1