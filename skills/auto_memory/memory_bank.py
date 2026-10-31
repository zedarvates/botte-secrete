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

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from skills.atomic_json import write_json

MEMORY_DIR = Path.home() / ".botte" / "memory"

_EXTERNAL_SOURCE_TYPES = {"repo", "web", "tool", "agent", "generated"}
_VALID_TRUST_CLASSES = {"trusted", "project", "external", "generated", "quarantined", "legacy"}


@dataclass(slots=True)
class MemoryEntry:
    """A single memory entry with provenance and trust metadata."""

    key: str
    value: Any
    category: str  # "user_pref", "pattern", "decision", "fact"
    confidence: float  # 0-1
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    access_count: int = 0
    tags: list[str] = field(default_factory=list)
    source_type: str = "local"
    source_id: str | None = None
    run_id: str | None = None
    trust_class: str = "project"
    executable_instruction: bool = False
    quarantined: bool = False

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
            "source_type": self.source_type,
            "source_id": self.source_id,
            "run_id": self.run_id,
            "trust_class": self.trust_class,
            "executable_instruction": self.executable_instruction,
            "quarantined": self.quarantined,
        }

    @classmethod
    def from_dict(cls, d: dict) -> MemoryEntry:
        """Load current and pre-provenance rows without granting instruction authority."""

        payload = dict(d)
        if "source_type" not in payload:
            payload["source_type"] = "legacy"
        if "trust_class" not in payload:
            payload["trust_class"] = "legacy"
        payload.setdefault("source_id", None)
        payload.setdefault("run_id", None)
        payload.setdefault("executable_instruction", False)
        # Preserve historical recall behaviour for existing local stores while
        # making their origin explicit. New external ingestion must use
        # store_external(), which is quarantined by default.
        payload.setdefault("quarantined", False)
        return cls(**payload)


class MemoryBank:
    """Persistent, searchable, provenance-aware memory bank."""

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
            except (json.JSONDecodeError, KeyError, TypeError):
                pass

    def _save_index(self):
        """Persist index to disk."""
        index_file = self.base / "index.json"
        data = [e.to_dict() for e in self._index.values()]
        write_json(index_file, data)

    @staticmethod
    def _validate_trust_class(trust_class: str) -> str:
        if trust_class not in _VALID_TRUST_CLASSES:
            raise ValueError(f"unsupported trust_class: {trust_class}")
        return trust_class

    def store(
        self,
        key: str,
        value: Any,
        category: str = "fact",
        confidence: float = 1.0,
        tags: list[str] | None = None,
        *,
        source_type: str = "local",
        source_id: str | None = None,
        run_id: str | None = None,
        trust_class: str = "project",
        executable_instruction: bool = False,
        quarantined: bool = False,
    ):
        """Store a local/project memory entry with explicit provenance.

        External observations should use :meth:`store_external` so they cannot
        silently enter normal recall paths.
        """

        if not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        self._validate_trust_class(trust_class)
        entry = MemoryEntry(
            key=key,
            value=value,
            category=category,
            confidence=confidence,
            tags=tags or [],
            source_type=source_type,
            source_id=source_id,
            run_id=run_id,
            trust_class=trust_class,
            executable_instruction=bool(executable_instruction),
            quarantined=bool(quarantined),
        )
        self._index[key] = entry
        self._save_index()

    def store_external(
        self,
        key: str,
        value: Any,
        *,
        source_type: str,
        source_id: str | None = None,
        run_id: str | None = None,
        category: str = "fact",
        confidence: float = 0.5,
        tags: list[str] | None = None,
    ) -> MemoryEntry:
        """Store untrusted external input in quarantine.

        External text is data, never executable policy. It is excluded from
        normal recall/search until an explicit promotion occurs.
        """

        if source_type not in _EXTERNAL_SOURCE_TYPES:
            raise ValueError(
                "store_external source_type must be one of: "
                + ", ".join(sorted(_EXTERNAL_SOURCE_TYPES))
            )
        self.store(
            key,
            value,
            category=category,
            confidence=confidence,
            tags=tags,
            source_type=source_type,
            source_id=source_id,
            run_id=run_id,
            trust_class="quarantined",
            executable_instruction=False,
            quarantined=True,
        )
        return self._index[key]

    def inspect(self, key: str) -> MemoryEntry | None:
        """Return entry metadata without changing trust/quarantine state."""
        return self._index.get(key)

    def recall(self, key: str, default: Any = None, *, include_quarantined: bool = False) -> Any:
        """Retrieve a memory entry, excluding quarantined data by default."""
        entry = self._index.get(key)
        if entry and (include_quarantined or not entry.quarantined):
            entry.access_count += 1
            entry.updated_at = time.time()
            self._save_index()
            return entry.value
        return default

    def search(
        self,
        query: str | None = None,
        category: str | None = None,
        min_confidence: float = 0.5,
        *,
        include_quarantined: bool = False,
    ) -> list[MemoryEntry]:
        """Search memories by query/category, excluding quarantine by default."""
        results = []
        for entry in self._index.values():
            if entry.quarantined and not include_quarantined:
                continue
            if entry.confidence < min_confidence:
                continue
            if category and entry.category != category:
                continue
            if query and query.lower() not in entry.key.lower():
                continue
            results.append(entry)
        return sorted(results, key=lambda e: e.confidence * max(e.access_count, 1), reverse=True)

    def promote(
        self,
        key: str,
        *,
        trust_class: str = "project",
        confidence: float | None = None,
    ) -> MemoryEntry:
        """Explicitly promote a quarantined entry while preserving provenance."""

        entry = self._index.get(key)
        if entry is None:
            raise KeyError(key)
        if trust_class in {"quarantined", "external", "generated"}:
            raise ValueError("promotion requires trust_class 'project' or 'trusted'")
        self._validate_trust_class(trust_class)
        if confidence is not None:
            if not 0.0 <= confidence <= 1.0:
                raise ValueError("confidence must be between 0 and 1")
            entry.confidence = confidence
        entry.trust_class = trust_class
        entry.quarantined = False
        # Promotion never grants executable authority implicitly.
        entry.executable_instruction = False
        entry.updated_at = time.time()
        self._save_index()
        return entry

    def forget(self, key: str):
        """Remove a memory entry."""
        self._index.pop(key, None)
        self._save_index()

    def consolidate(self):
        """Merge similar non-quarantined memories and reduce noise."""
        groups: dict[str, list[MemoryEntry]] = {}
        for key, entry in list(self._index.items()):
            if entry.quarantined:
                continue
            prefix = key.split(".")[0] if "." in key else key
            groups.setdefault(prefix, []).append(entry)

        for _prefix, entries in groups.items():
            if len(entries) > 1:
                best = max(entries, key=lambda e: e.confidence * max(e.access_count, 1))
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
            "quarantined_entries": sum(1 for e in self._index.values() if e.quarantined),
            "by_category": dict(sorted({
                c: sum(1 for e in self._index.values() if e.category == c)
                for c in {e.category for e in self._index.values()}
            }.items())),
            "by_source_type": dict(sorted({
                s: sum(1 for e in self._index.values() if e.source_type == s)
                for s in {e.source_type for e in self._index.values()}
            }.items())),
            "total_accesses": sum(e.access_count for e in self._index.values()),
        }
