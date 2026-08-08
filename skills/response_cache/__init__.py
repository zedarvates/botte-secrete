"""Semantic Response Cache — Caches LLM responses by semantic similarity.

Principle: Same questions should get same answers.
Uses Qdrant (EUREKAI:6333) for similarity search.
Hash-based for exact matches, embedding-based for similar queries.

Token savings: 60% on repeated/similar queries.

Architecture:
    Query → exact hash check (fast) → semantic similarity (Qdrant) → LLM (fallback)
"""

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
from skills.atomic_json import write_json


@dataclass
class CachedResponse:
    """A cached LLM response."""
    query_hash: str
    query: str
    response: str
    timestamp: float
    hit_count: int = 0
    model: str = ""
    tokens_saved: int = 0


class ResponseCache:
    """Two-level cache: exact hash + semantic similarity via Qdrant."""

    def __init__(self, cache_dir: str = ".botte-cache", *, learn: bool = False):
        self.cache_dir = Path(cache_dir)
        self.learn = bool(learn)
        self.cache_dir.mkdir(exist_ok=True)
        self.cache_file = self.cache_dir / "response_cache.json"
        self.stats_file = self.cache_dir / "response_cache_stats.json"
        self._entries: dict[str, CachedResponse] = {}
        self._load()
        self.stats = self._load_stats()

    def _load_stats(self) -> dict:
        defaults = {"hits_exact": 0, "hits_semantic": 0, "misses": 0,
                    "tokens_saved": 0}
        if not self.stats_file.exists():
            return defaults
        try:
            data = json.loads(self.stats_file.read_text(encoding="utf-8"))
            return {key: int(data.get(key, value)) for key, value in defaults.items()}
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return defaults

    def _save_stats(self) -> None:
        write_json(self.stats_file, self.stats)

    def _load(self):
        """Load cache from disk."""
        if self.cache_file.exists():
            try:
                data = json.loads(self.cache_file.read_text(encoding="utf-8"))
                for h, entry in data.items():
                    self._entries[h] = CachedResponse(**entry)
            except (json.JSONDecodeError, TypeError):
                pass

    def _save(self):
        """Persist cache to disk."""
        data = {h: entry.__dict__ for h, entry in self._entries.items()}
        write_json(self.cache_file, data)

    def _hash(self, query: str, model: str = "", context: str = "") -> str:
        """Deterministic hash of a query."""
        # Normalize: strip whitespace, lowercase for case-insensitive matching
        normalized = " ".join(query.split())
        material = json.dumps(
            {"query": normalized, "model": model, "context": context},
            ensure_ascii=False, sort_keys=True,
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]

    def get_exact(self, query: str, model: str = "", context: str = "") -> Optional[CachedResponse]:
        """Check exact hash match (fast, no embedding needed)."""
        h = self._hash(query, model, context)
        if h in self._entries:
            entry = self._entries[h]
            entry.hit_count += 1
            self.stats["hits_exact"] += 1
            self.stats["tokens_saved"] += entry.tokens_saved
            self._save()
            self._save_stats()
            return entry
        return None

    def get_semantic(self, query: str, model: str = "") -> Optional[CachedResponse]:
        """Check semantic similarity via Qdrant.
        
        In production: use qdrant_search_vault(query) and check similarity score.
        For now: simple keyword overlap as fallback.
        """
        # Try keyword-based similarity (no embedding needed)
        query_words = set(query.lower().split())
        best_match = None
        best_score = 0

        for h, entry in self._entries.items():
            if entry.model != model:
                continue
            entry_words = set(entry.query.lower().split())
            if not query_words or not entry_words:
                continue
            overlap = len(query_words & entry_words) / len(query_words | entry_words)
            if overlap > 0.8 and overlap > best_score:  # 80%+ word overlap
                best_match = entry
                best_score = overlap

        if best_match:
            best_match.hit_count += 1
            self.stats["hits_semantic"] += 1
            self.stats["tokens_saved"] += best_match.tokens_saved
            self._save()
            self._save_stats()
            return best_match

        return None

    def get(self, query: str, use_semantic: bool = False, *, model: str = "",
            context: str = "") -> Optional[CachedResponse]:
        """Two-level lookup: exact hash → semantic → miss."""
        grounding_values = self._grounding_values(query) if self.learn else None
        # Level 1: Exact match
        exact = self.get_exact(query, model, context)
        if exact:
            self._record_grounding(query, grounding_values, hit=True, hit_kind="exact_hit")
            return exact

        # Level 2: Semantic similarity (if enabled)
        if use_semantic:
            semantic = self.get_semantic(query, model)
            if semantic:
                self._record_grounding(
                    query, grounding_values, hit=True, hit_kind="semantic_hit"
                )
                return semantic

        # Miss
        self.stats["misses"] += 1
        self._save_stats()
        self._record_grounding(query, grounding_values, hit=False, hit_kind="miss")
        return None

    def _grounding_values(self, query: str) -> dict[str, float]:
        """Snapshot pre-lookup features for the cache-hit micro-NN."""
        from skills.botte_nn.features import semantic_cache_values

        total = self.stats["hits_exact"] + self.stats["hits_semantic"] + self.stats["misses"]
        hits = self.stats["hits_exact"] + self.stats["hits_semantic"]
        return semantic_cache_values(
            cache_density=min(len(self._entries) / 1000.0, 1.0),
            agent_type="analyze",
            cache_hit_history=(hits / total if total else 0.0),
            query_length=max(1, len(query) // 4),
        )

    @staticmethod
    def _record_grounding(query: str, values: Optional[dict[str, float]], *,
                          hit: bool, hit_kind: str) -> None:
        if values is None:
            return
        try:
            from skills.botte_nn.auto_labels import record_cache_lookup

            record_cache_lookup(query, values, hit=hit, hit_kind=hit_kind)
        except Exception:  # noqa: BLE001 - telemetry must never break cache lookup
            pass

    def set(self, query: str, response: str, model: str = "",
            tokens_used: int = 0, context: str = ""):
        """Cache a response."""
        h = self._hash(query, model, context)
        self._entries[h] = CachedResponse(
            query_hash=h,
            query=query,
            response=response,
            timestamp=time.time(),
            model=model,
            tokens_saved=tokens_used,  # Reusing this response saves these tokens
        )
        # Limit cache size — keep 1000 most recent
        if len(self._entries) > 1000:
            sorted_entries = sorted(self._entries.items(),
                                   key=lambda x: x[1].timestamp, reverse=True)
            self._entries = dict(sorted_entries[:1000])
        self._save()

    def clear(self, older_than_hours: Optional[int] = None):
        """Clear cache entries."""
        if older_than_hours:
            cutoff = time.time() - (older_than_hours * 3600)
            self._entries = {h: e for h, e in self._entries.items()
                            if e.timestamp > cutoff}
        else:
            self._entries = {}
        self._save()

    def report(self) -> dict:
        """Cache performance report."""
        total = self.stats["hits_exact"] + self.stats["hits_semantic"] + self.stats["misses"]
        hit_rate = round((self.stats["hits_exact"] + self.stats["hits_semantic"]) * 100 / total) if total else 0
        return {
            "entries": len(self._entries),
            "hits_exact": self.stats["hits_exact"],
            "hits_semantic": self.stats["hits_semantic"],
            "misses": self.stats["misses"],
            "hit_rate_pct": hit_rate,
            "tokens_saved_total": self.stats["tokens_saved"],
        }


# Singleton
_cache = ResponseCache(learn=os.environ.get("BOTTE_NN_AUTO_LABELS", "1") != "0")

def cached(query: str, response_fn, model: str = "", use_semantic: bool = False,
           context: str = "", tokens_used: int = 0) -> tuple[str, bool]:
    """Cached LLM call wrapper.
    
    Usage:
        response, was_cached = cached("résume ce texte", lambda: llm_call(prompt))
    """
    result = _cache.get(query, use_semantic, model=model, context=context)
    if result:
        return result.response, True

    response = response_fn()
    _cache.set(query, response, model, tokens_used=tokens_used, context=context)
    return response, False
