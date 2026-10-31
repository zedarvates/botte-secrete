"""
Noise compressor for AutoMemory — reduces memory size via pattern recognition.

Inspired by WM v2 (noise injection + bottleneck for generalization).
"""

from __future__ import annotations

import json
import re
from collections import Counter

from skills.auto_memory.memory_bank import MemoryBank, MemoryEntry


def compress_memories(bank: MemoryBank, threshold: int = 3) -> int:
    """Find and compress similar trusted memories, returning count of merges.

    Quarantined entries are evidence awaiting review. They must not be merged,
    rewritten, or deleted by an automatic noise-reduction pass because doing so
    can destroy provenance or accidentally promote attacker-controlled content.
    """
    merged = 0
    entries = [entry for entry in bank._index.values() if not entry.quarantined]
    seen: dict[str, MemoryEntry] = {}

    for entry in entries:
        norm_key = _normalize_key(entry.key)
        if norm_key in seen:
            existing = seen[norm_key]
            existing.tags = list(set(existing.tags) | set(entry.tags))
            existing.access_count += entry.access_count
            existing.updated_at = max(existing.updated_at, entry.updated_at)
            bank._index.pop(entry.key, None)
            merged += 1
        else:
            seen[norm_key] = entry

    bank._save_index()
    return merged


def _normalize_key(key: str) -> str:
    """Normalize a key for similarity matching."""
    return re.sub(r'_\d+$', '', key.lower()).replace('-', '_')


def extract_patterns(entries: list[MemoryEntry], *, include_quarantined: bool = False) -> list[dict]:
    """Extract common patterns without consuming quarantined text by default."""
    patterns = []
    eligible = entries if include_quarantined else [e for e in entries if not e.quarantined]
    text_entries = [e for e in eligible if isinstance(e.value, str)]

    all_text = "\n".join(e.value for e in text_entries if isinstance(e.value, str))
    word_counts = Counter(all_text.split())
    common_words = [w for w, c in word_counts.most_common(10) if c > 1]

    if common_words:
        patterns.append({"type": "common_words", "words": common_words[:5]})

    json_keys = set()
    for e in text_entries:
        try:
            data = json.loads(e.value)
            if isinstance(data, dict):
                json_keys.update(data.keys())
        except (json.JSONDecodeError, TypeError):
            pass

    if json_keys:
        patterns.append({"type": "json_keys", "keys": list(json_keys)[:10]})

    return patterns


def bottleneck_compress(bank: MemoryBank, keep_pct: float = 0.3) -> int:
    """Reduce non-quarantined memory while preserving review evidence."""
    entries = [entry for entry in bank._index.values() if not entry.quarantined]
    if not entries:
        return 0

    entries.sort(key=lambda e: e.confidence * e.access_count, reverse=True)
    keep_count = max(1, int(len(entries) * keep_pct))

    removed = 0
    for entry in entries[keep_count:]:
        bank._index.pop(entry.key, None)
        removed += 1

    bank._save_index()
    return removed
