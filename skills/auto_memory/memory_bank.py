"""
AutoMemory — Memory as a learnable skill for botte-secrete.

Inspired by Stanford AutoMem (memory as capability, not just storage).
Adapts to patterns in agent behavior and reduces noise.

Usage:
    from skills.auto_memory.memory_bank import MemoryBank
    bank = MemoryBank()
    bank.store("user_pref", {"format": "concise", "language": "fr"})
    prefs = bank.recall("user_pref")
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from skills.atomic_json import write_json

MEMORY_DIR = Path.home() / ".botte" / "memory"


@dataclass(slots=True)
class MemoryEntry:
    """A single memory entry with metadata."""
    key: str
    value: Any
    category: str  # "user_pref", "pattern", "decision", "fact"
    confidence: float  # 0-1
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    access_count: int = 0
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "value": self.value,
            "category": self.category,
            "confidence": self.confidence,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "access_count": self.access_count,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, d: dict) -> MemoryEntry:
        return cls(**d)


class MemoryBank:
    """Persistent, searchable, compressible memory bank."""

    def __init__(self, base_dir: Path | None = None):
        self.base = Path(base_dir) if base_dir else MEMORY_DIR
        self.base.mkdir(parents=True, exist_ok=True)
        self._index: dict[str, MemoryEntry] = {}
        self._load_index()

    def _load_index(self):
        """Load index from disk."""
        index_file = self.base / "index.json"
        if index_file.exists():
            try:
                data = json.loads(index_file.read_text(encoding="utf-8"))
                for d in data:
                    self._index[d["key"]] = MemoryEntry.from_dict(d)
            except (json.JSONDecodeError, KeyError):
                pass

    def _save_index(self):
        """Persist index to disk."""
        index_file = self.base / "index.json"
        data = [e.to_dict() for e in self._index.values()]
        write_json(index_file, data)

    def store(self, key: str, value: Any, category: str = "fact",
              confidence: float = 1.0, tags: list[str] | None = None):
        """Store a memory entry."""
        entry = MemoryEntry(
            key=key,
            value=value,
            category=category,
            confidence=confidence,
            tags=tags or [],
        )
        self._index[key] = entry
        self._save_index()

    def recall(self, key: str, default: Any = None) -> Any:
        """Retrieve a memory entry."""
        entry = self._index.get(key)
        if entry:
            entry.access_count += 1
            entry.updated_at = time.time()
            self._save_index()
            return entry.value
        return default

    def search(self, query: str | None = None, category: str | None = None,
               min_confidence: float = 0.5) -> list[MemoryEntry]:
        """Search memories by query or category."""
        results = []
        for entry in self._index.values():
            if entry.confidence < min_confidence:
                continue
            if category and entry.category != category:
                continue
            if query:
                if query.lower() not in entry.key.lower():
                    continue
            results.append(entry)
        return sorted(results, key=lambda e: e.confidence * e.access_count, reverse=True)

    def forget(self, key: str):
        """Remove a memory entry."""
        self._index.pop(key, None)
        self._save_index()

    def consolidate(self):
        """Merge similar memories and reduce noise."""
        # Group by key prefix
        groups: dict[str, list[MemoryEntry]] = {}
        for key, entry in list(self._index.items()):
            prefix = key.split(".")[0] if "." in key else key
            groups.setdefault(prefix, []).append(entry)

        for prefix, entries in groups.items():
            if len(entries) > 1:
                # Keep highest confidence, merge tags
                best = max(entries, key=lambda e: e.confidence * e.access_count)
                for e in entries:
                    if e != best:
                        best.tags = list(set(best.tags) | set(e.tags))
                        self._index.pop(e.key, None)
                best.updated_at = time.time()

        self._save_index()

    def stats(self) -> dict:
        """Return memory bank statistics."""
        return {
            "total_entries": len(self._index),
            "by_category": dict(sorted({
                c: sum(1 for e in self._index.values() if e.category == c)
                for c in {e.category for e in self._index.values()}
            }.items())),
            "total_accesses": sum(e.access_count for e in self._index.values()),
        }
