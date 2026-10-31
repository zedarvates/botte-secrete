"""Persistent exact-response cache with optional lexical-similarity lookup.

Cooperating processes serialize disk transactions. Model and context are part
of the identity; only a context fingerprint is persisted. This module calls no
provider or vector database. Counters reflect caller-reported token usage,
not measured billing savings. Semantic supervision remains explicitly opt-in.
"""

import hashlib
from contextlib import contextmanager
import errno
from functools import wraps
import json
import math
import os
from threading import RLock
import time
from pathlib import Path
from typing import Optional
from dataclasses import dataclass
from skills.atomic_json import write_json


def _serialized(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self._transaction():
            return method(self, *args, **kwargs)
    return wrapped


@dataclass
class CachedResponse:
    """A cached LLM response."""
    query_hash: str
    query: str
    response: str
    timestamp: float
    hit_count: int = 0
    model: str = ""
    context_hash: str = ""
    tokens_saved: int = 0


class ResponseCache:
    """Two-level cache: exact hash + semantic similarity via Qdrant."""

    def __init__(self, cache_dir: str = ".botte-cache", *, learn: bool = False,
                 semantic_shadow: bool = False):
        self.cache_dir = Path(cache_dir)
        self.learn = bool(learn)
        self.semantic_shadow = bool(semantic_shadow)
        self.cache_dir.mkdir(exist_ok=True)
        self.cache_file = self.cache_dir / "response_cache.json"
        self.stats_file = self.cache_dir / "response_cache_stats.json"
        self._entries: dict[str, CachedResponse] = {}
        self._thread_lock = RLock()
        self._transaction_depth = 0
        with self._transaction():
            pass

    @contextmanager
    def _transaction(self):
        """Refresh disk state under one stable, cooperative process lock.

        Nested public calls reuse their transaction; the thread lock prevents
        another thread from mistaking that nesting for its own transaction.
        Older versions do not participate in this lock protocol.
        """
        with self._thread_lock:
            if self._transaction_depth:
                yield
                return
            with (self.cache_dir / "response_cache.lock").open("a+b") as lock:
                lock.seek(0, os.SEEK_END)
                if lock.tell() == 0:
                    lock.write(b"\0")
                    lock.flush()
                deadline = time.monotonic() + 2
                while True:
                    lock.seek(0)
                    try:
                        if os.name == "nt":
                            import msvcrt
                            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                        else:
                            import fcntl
                            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except OSError as error:
                        if error.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                            raise
                        if time.monotonic() >= deadline:
                            raise TimeoutError("Response cache busy") from None
                        time.sleep(.01)
                try:
                    self._load()
                    self.stats = self._load_stats()
                    self._transaction_depth = 1
                    yield
                finally:
                    self._transaction_depth = 0
                    lock.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _load_stats(self) -> dict:
        defaults = {"hits_exact": 0, "hits_semantic": 0, "misses": 0,
                    "semantic_attempt_hits": 0, "semantic_attempt_misses": 0,
                    "semantic_shadow_hits": 0, "semantic_shadow_misses": 0,
                    "tokens_saved": 0}
        if not self.stats_file.exists():
            return defaults
        try:
            data = json.loads(self.stats_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return defaults
            return {key: int(data.get(key, value)) for key, value in defaults.items()}
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return defaults

    def _save_stats(self) -> None:
        write_json(self.stats_file, self.stats)

    def _load(self):
        """Replace the snapshot; missing or invalid state cannot resurrect it."""
        self._entries = {}
        if self.cache_file.exists():
            try:
                data = json.loads(self.cache_file.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    return
                entries = {h: CachedResponse(**entry) for h, entry in data.items()}
                if any(isinstance(e.timestamp, bool) or not isinstance(e.timestamp, (int, float))
                       or not math.isfinite(e.timestamp) for e in entries.values()):
                    return
                self._entries = entries
            except (OSError, ValueError, TypeError):
                pass

    def _save(self):
        """Persist cache to disk."""
        data = {h: entry.__dict__ for h, entry in self._entries.items()}
        write_json(self.cache_file, data)

    def _hash(self, query: str, model: str = "", context: str = "") -> str:
        """Deterministic hash of a query."""
        # Exact identity includes whitespace, including indentation and quoted text.
        material = json.dumps(
            {"query": query, "model": model, "context": context},
            ensure_ascii=False, sort_keys=True,
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _context_hash(context: str) -> str:
        """Fingerprint a system context without persisting its contents."""
        return hashlib.sha256(context.encode("utf-8")).hexdigest()

    @_serialized
    def get_exact(self, query: str, model: str = "", context: str = "") -> Optional[CachedResponse]:
        """Check exact hash match (fast, no embedding needed)."""
        h = self._hash(query, model, context)
        if h in self._entries:
            entry = self._entries[h]
            # Legacy keys collapsed whitespace. Reject a different stored query
            # before recording a hit; noncanonical legacy queries need recaching.
            if entry.query != query or entry.model != model:
                return None
            entry.hit_count += 1
            self.stats["hits_exact"] += 1
            self.stats["tokens_saved"] += entry.tokens_saved
            self._save()
            self._save_stats()
            return entry
        return None

    def _find_semantic(self, query: str, model: str = "",
                       context: str = "") -> Optional[CachedResponse]:
        """Find the best semantic candidate without mutating cache state."""
        query_words = set(query.lower().split())
        context_hash = self._context_hash(context)
        best_match = None
        best_score = 0

        for entry in self._entries.values():
            if (entry.model != model
                    or entry.context_hash != context_hash):
                continue
            entry_words = set(entry.query.lower().split())
            if not query_words or not entry_words:
                continue
            overlap = len(query_words & entry_words) / len(query_words | entry_words)
            if overlap > 0.8 and overlap > best_score:  # 80%+ word overlap
                best_match = entry
                best_score = overlap

        return best_match

    @_serialized
    def get_semantic(self, query: str, model: str = "",
                     context: str = "") -> Optional[CachedResponse]:
        """Check semantic similarity and account for a served lookup.

        In production: use qdrant_search_vault(query) and check similarity score.
        For now: simple keyword overlap as fallback.
        """
        best_match = self._find_semantic(query, model, context)

        if best_match:
            best_match.hit_count += 1
            self.stats["hits_semantic"] += 1
            self.stats["semantic_attempt_hits"] += 1
            self.stats["tokens_saved"] += best_match.tokens_saved
            self._save()
            self._save_stats()
            return best_match

        self.stats["semantic_attempt_misses"] += 1
        self._save_stats()
        return None

    def _record_semantic_shadow(self, hit: bool) -> None:
        """Account for an observation-only semantic attempt."""
        key = "semantic_shadow_hits" if hit else "semantic_shadow_misses"
        self.stats[key] += 1
        self._save_stats()

    @_serialized
    def get(self, query: str, use_semantic: bool = False, *, model: str = "",
            context: str = "") -> Optional[CachedResponse]:
        """Two-level lookup: exact hash → semantic → miss."""
        # Level 1: Exact match
        exact = self.get_exact(query, model, context)
        if exact:
            return exact

        # Level 2: Semantic similarity (if enabled)
        if use_semantic:
            # The micro-NN target is conditional on a real semantic attempt.
            # Exact hits and lookups that skip this level are different events
            # and must not pollute its training ledger.
            grounding_values = (
                self._grounding_values(query, model, context)
                if self.learn else None
            )
            semantic = self.get_semantic(query, model, context)
            if semantic:
                self._record_grounding(
                    query, grounding_values, hit=True, hit_kind="semantic_hit"
                )
                return semantic
        elif self.learn and self.semantic_shadow:
            # Observation only: inspect the candidate but never serve it or
            # increment its hit_count/tokens_saved counters.
            grounding_values = self._grounding_values(query, model, context)
            shadow_hit = self._find_semantic(query, model, context) is not None
            self._record_semantic_shadow(shadow_hit)
            self._record_grounding(
                query, grounding_values, hit=shadow_hit,
                hit_kind=(
                    "semantic_shadow_hit" if shadow_hit
                    else "semantic_shadow_miss"
                ),
            )

        # Miss
        self.stats["misses"] += 1
        self._save_stats()
        if use_semantic:
            self._record_grounding(
                query, grounding_values, hit=False, hit_kind="semantic_miss"
            )
        return None

    def _grounding_values(self, query: str, model: str = "",
                          context: str = "") -> dict[str, float]:
        """Snapshot pre-lookup features for the cache-hit micro-NN."""
        from skills.botte_nn.features import semantic_cache_values

        context_hash = self._context_hash(context)
        eligible = [
            entry for entry in self._entries.values()
            if entry.model == model and entry.context_hash == context_hash
        ]
        query_tokens = query.lower().split()
        query_words = set(query_tokens)
        eligible_vocabulary = {
            word for entry in eligible for word in entry.query.lower().split()
        }
        vocabulary_coverage = (
            len(query_words & eligible_vocabulary) / len(query_words)
            if query_words else 0.0
        )
        query_length = len(query_tokens)
        length_tolerance = max(2, round(query_length * 0.2))
        length_neighbors = sum(
            abs(len(entry.query.split()) - query_length) <= length_tolerance
            for entry in eligible
        )
        semantic_attempts = (
            self.stats["semantic_attempt_hits"]
            + self.stats["semantic_attempt_misses"]
            + self.stats["semantic_shadow_hits"]
            + self.stats["semantic_shadow_misses"]
        )
        semantic_hits = (
            self.stats["semantic_attempt_hits"]
            + self.stats["semantic_shadow_hits"]
        )
        return semantic_cache_values(
            query,
            cache_density=min(len(self._entries) / 1000.0, 1.0),
            eligible_cache_density=min(len(eligible) / 1000.0, 1.0),
            eligible_vocabulary_coverage=vocabulary_coverage,
            length_neighbor_ratio=(
                length_neighbors / len(eligible) if eligible else 0.0
            ),
            cache_hit_history=(
                semantic_hits / semantic_attempts
                if semantic_attempts else 0.0
            ),
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

    @_serialized
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
            context_hash=self._context_hash(context),
            tokens_saved=tokens_used,  # Reusing this response saves these tokens
        )
        # Limit cache size — keep 1000 most recent
        if len(self._entries) > 1000:
            sorted_entries = sorted(self._entries.items(),
                                   key=lambda x: x[1].timestamp, reverse=True)
            self._entries = dict(sorted_entries[:1000])
        self._save()

    @_serialized
    def clear(self, older_than_hours: Optional[int] = None):
        """Clear cache entries."""
        if older_than_hours is not None:
            if (isinstance(older_than_hours, bool)
                    or not isinstance(older_than_hours, (int, float))
                    or not math.isfinite(older_than_hours) or older_than_hours < 0):
                raise ValueError("older_than_hours must be finite and non-negative")
            cutoff = time.time() - (older_than_hours * 3600)
            self._entries = {h: e for h, e in self._entries.items()
                            if e.timestamp > cutoff}
        else:
            self._entries = {}
        self._save()

    @_serialized
    def report(self) -> dict:
        """Cache performance report."""
        total = self.stats["hits_exact"] + self.stats["hits_semantic"] + self.stats["misses"]
        hit_rate = round((self.stats["hits_exact"] + self.stats["hits_semantic"]) * 100 / total) if total else 0
        served_semantic_attempts = (
            self.stats["semantic_attempt_hits"]
            + self.stats["semantic_attempt_misses"]
        )
        shadow_semantic_attempts = (
            self.stats["semantic_shadow_hits"]
            + self.stats["semantic_shadow_misses"]
        )
        semantic_attempts = served_semantic_attempts + shadow_semantic_attempts
        semantic_hits = (
            self.stats["semantic_attempt_hits"]
            + self.stats["semantic_shadow_hits"]
        )
        return {
            "entries": len(self._entries),
            "hits_exact": self.stats["hits_exact"],
            "hits_semantic": self.stats["hits_semantic"],
            "misses": self.stats["misses"],
            "hit_rate_pct": hit_rate,
            "semantic_attempts": semantic_attempts,
            "semantic_served_attempts": served_semantic_attempts,
            "semantic_shadow_attempts": shadow_semantic_attempts,
            "semantic_hit_rate_pct": round(
                semantic_hits * 100 / semantic_attempts
            ) if semantic_attempts else 0,
            "tokens_saved_total": self.stats["tokens_saved"],
            "token_savings_basis": "caller_reported_usage_not_billing_proof",
        }


# Singleton
_cache = ResponseCache(
    learn=os.environ.get("BOTTE_NN_AUTO_LABELS", "1") != "0",
    semantic_shadow=os.environ.get("BOTTE_NN_SEMANTIC_SHADOW", "0") == "1",
)

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
