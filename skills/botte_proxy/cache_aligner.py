"""CacheAligner — stabilise les préfixes de prompt pour les KV caches.

Les providers LLM (Anthropic, OpenAI, Google) cachent le KV state des
préfixes de prompt. Si deux requêtes partagent le même préfixe (même bytes),
la seconde économise ~50-90% du calcul d'input.

CacheAligner fait trois choses :
1. Normalise les préfixes — supprime les sources de variation (timestamps, IDs, nombres aléatoires)
2. Structure les messages — système + historique en tête pour maximiser le préfixe partagé
3. Track les stats — combien de fois le cache a potentiellement hit
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Optional


# ── Patterns to normalize ──────────────────────────────────────

# Replace timestamps/date patterns with stable placeholders
TIMESTAMP_PATTERNS = [
    (re.compile(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?'), '<TS>'),
    (re.compile(r'\d{4}-\d{2}-\d{2}'), '<DATE>'),
    (re.compile(r'\d{2}:\d{2}:\d{2}(\.\d+)?'), '<TIME>'),
]

# Replace UUIDs and long hex hashes
UUID_PATTERN = re.compile(
    r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
    re.IGNORECASE,
)
HASH_PATTERN = re.compile(r'\b[0-9a-f]{16,}\b', re.IGNORECASE)

# Replace file paths (keeping structure but removing user-specific parts)
PATH_PATTERN = re.compile(
    r'(/home/[^/\s]+|/Users/[^/\s]+|/mnt/[^/\s]+|C:\\Users\\[^\\\s]+)',
    re.IGNORECASE,
)

# Replace IP addresses
IP_PATTERN = re.compile(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(:\d+)?\b')

# Replace port numbers
PORT_PATTERN = re.compile(r':(\d{4,5})\b')

# Replace process IDs
PID_PATTERN = re.compile(r'\b(pid|PID):?\s*\d+\b')


def normalize_text(text: str) -> str:
    """Normalize a text to remove sources of cache-miss variation.

    Strips timestamps, UUIDs, absolute paths, IPs, and other
    instance-specific data that would cause the KV cache to miss.
    """
    result = text
    for pattern, replacement in TIMESTAMP_PATTERNS:
        result = pattern.sub(replacement, result)
    result = UUID_PATTERN.sub('<UUID>', result)
    result = HASH_PATTERN.sub('<HASH>', result)
    result = PATH_PATTERN.sub('<HOME>', result)
    result = IP_PATTERN.sub('<IP>', result)
    result = PID_PATTERN.sub('pid:<PID>', result)
    return result


def normalize_messages(messages: list[dict]) -> list[dict]:
    """Normalize a messages array for cache alignment.

    Returns a new list with all variable content normalized.
    """
    result = []
    for msg in messages:
        new_msg = dict(msg)
        content = msg.get("content", "")
        if isinstance(content, str):
            new_msg["content"] = normalize_text(content)
        elif isinstance(content, list):
            # Handle content arrays (multimodal messages)
            new_parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    part = dict(part)
                    part["text"] = normalize_text(part["text"])
                new_parts.append(part)
            new_msg["content"] = new_parts
        result.append(new_msg)
    return result


# ── Prefix cache ───────────────────────────────────────────────

@dataclass
class CacheEntry:
    """A tracked cache prefix."""
    prefix_hash: str
    system_prompt_hash: str
    first_messages: tuple[str, ...]  # hashes of first few messages
    count: int = 1
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    total_input_tokens: int = 0
    estimated_saved_tokens: int = 0


class CacheAligner:
    """Aligns message prefixes so provider KV caches hit.

    Tracks recent system prompts and message prefixes, normalizes them,
    and reports cache alignment statistics.

    The key insight: most LLM providers cache the KV state of the prompt
    prefix. If you send the exact same prefix bytes, the cache hits and
    you save compute (and thus money) on the cached portion.
    """

    def __init__(self, max_entries: int = 100):
        self.max_entries = max_entries
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self.total_requests = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self._last_prefix_hash: Optional[str] = None

    def _hash_text(self, text: str) -> str:
        """Stable hash of normalized text."""
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    def _extract_prefix_key(self, messages: list[dict]) -> str:
        """Extract a cache key from the message prefix.

        The key is the hash of: system prompt + first 2 messages.
        This represents the shared prefix that would be cached.
        """
        key_parts = []
        for i, msg in enumerate(messages):
            if i >= 3:  # System + first 2 messages = cache prefix
                break
            content = str(msg.get("content", ""))
            if isinstance(content, str):
                normalized = normalize_text(content)
                key_parts.append(self._hash_text(normalized))
        return ":".join(key_parts)

    def align(self, messages: list[dict]) -> tuple[list[dict], dict]:
        """Align messages for cache optimization.

        Steps:
        1. Normalize variable content (timestamps, paths, etc.)
        2. Compute prefix hash for cache hit detection
        3. Track stats

        Returns:
            (aligned_messages, cache_info)
            cache_info = {"hit": bool, "prefix_hash": str, 
                         "estimated_savings": int}
        """
        self.total_requests += 1

        # Normalize
        aligned = normalize_messages(messages)

        # Compute prefix key
        prefix_key = self._extract_prefix_key(aligned)
        prefix_hash = self._hash_text(prefix_key)

        # Check for cache hit
        cache_hit = prefix_hash == self._last_prefix_hash
        if cache_hit:
            self.cache_hits += 1
        else:
            self.cache_misses += 1
        self._last_prefix_hash = prefix_hash

        # Update cache entry
        if prefix_hash in self._cache:
            entry = self._cache[prefix_hash]
            entry.count += 1
            entry.last_seen = time.time()
            # Move to end (most recently used)
            self._cache.move_to_end(prefix_hash)
        else:
            entry = CacheEntry(
                prefix_hash=prefix_hash,
                system_prompt_hash=self._hash_text(
                    normalize_text(str(messages[0].get("content", "")))
                ) if messages else "",
                first_messages=tuple(
                    self._hash_text(normalize_text(str(m.get("content", ""))))
                    for m in messages[:2]
                ),
            )
            self._cache[prefix_hash] = entry
            if len(self._cache) > self.max_entries:
                self._cache.popitem(last=False)  # Remove oldest

        # Estimate tokens saved by cache hit
        estimated_saved = 0
        if cache_hit:
            # Rough estimate: if prefix is same, ~60% of input tokens are cached
            total_input_chars = sum(
                len(str(m.get("content", "")))
                for m in aligned
            )
            estimated_saved = total_input_chars // 4 * 60 // 100  # ~60% of input
            entry.estimated_saved_tokens += estimated_saved

        entry.total_input_tokens += sum(
            len(str(m.get("content", ""))) // 4
            for m in aligned
        )

        return aligned, {
            "hit": cache_hit,
            "prefix_hash": prefix_hash,
            "estimated_saved_tokens": estimated_saved,
            "consecutive_hits": self.cache_hits,
            "consecutive_misses": self.cache_misses,
        }

    def stats(self) -> dict:
        """Return cache alignment statistics."""
        total = self.cache_hits + self.cache_misses
        hit_rate = round(self.cache_hits / total * 100, 1) if total > 0 else 0.0
        return {
            "total_requests": self.total_requests,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "hit_rate_pct": hit_rate,
            "unique_prefixes": len(self._cache),
            "total_estimated_saved_tokens": sum(
                e.estimated_saved_tokens for e in self._cache.values()
            ),
            "top_prefixes": [
                {
                    "hash": h,
                    "count": e.count,
                    "saved_tokens": e.estimated_saved_tokens,
                    "first_seen": time.ctime(e.first_seen),
                }
                for h, e in list(self._cache.items())[:10]
            ],
        }


# Singleton
_aligner = CacheAligner()


def get_aligner() -> CacheAligner:
    return _aligner


def align_messages(messages: list[dict]) -> tuple[list[dict], dict]:
    """Convenience: align messages for cache optimization."""
    return _aligner.align(messages)


def cache_stats() -> dict:
    """Convenience: get cache alignment stats."""
    return _aligner.stats()
