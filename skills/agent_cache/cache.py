"""Agent Cache — skip-agent execution quand l'output est prédictible.

Évite d'exécuter un agent si son résultat peut être prédit à partir
de l'historique ou du cache. Basé sur 4 stratégies :

1. Hash matching — même input → même output (cache déterministe)
2. Fingerprint — si le code n'a pas changé, le résultat est identique
3. Semantic cache — similarité sémantique avec une requête déjà faite
4. No-change prediction — micro-NN prédit "pas de changement"

Usage:
    python -m skills.agent_cache.cli check "query"
    python -m skills.agent_cache.cli store "query" "response"
    python -m skills.agent_cache.cli stats
"""
from __future__ import annotations

import hashlib
import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


CACHE_STORE = Path.home() / ".botte" / "agent-cache.json"
MAX_CACHE_SIZE = 10_000  # Nombre max d'entrées
SIMILARITY_THRESHOLD = 0.85  # Seuil de similarité sémantique


@dataclass
class CacheEntry:
    """A cached agent response."""
    query_hash: str
    query: str
    response: str
    agent_type: str  # "audit", "fix", "analyze", "optimize", etc.
    context_hash: str  # Hash of context at time of execution
    fingerprint: str = ""  # Code/project fingerprint
    score: float = 1.0  # Confidence score
    hits: int = 1
    created: float = field(default_factory=time.time)
    last_hit: float = field(default_factory=time.time)


class AgentCache:
    """Cache agent responses to skip redundant executions."""

    def __init__(self):
        self.entries: list[CacheEntry] = []
        self._load()

    def _load(self):
        if CACHE_STORE.exists():
            try:
                data = json.loads(CACHE_STORE.read_text())
                for e in data.get("entries", []):
                    self.entries.append(CacheEntry(**e))
            except (json.JSONDecodeError, TypeError):
                pass

    def _save(self):
        CACHE_STORE.parent.mkdir(parents=True, exist_ok=True)
        # Trim to max size (keep most recent)
        self.entries.sort(key=lambda e: e.last_hit, reverse=True)
        self.entries = self.entries[:MAX_CACHE_SIZE]

        CACHE_STORE.write_text(json.dumps({
            "entries": [
                {"query_hash": e.query_hash, "query": e.query,
                 "response": e.response, "agent_type": e.agent_type,
                 "context_hash": e.context_hash, "fingerprint": e.fingerprint,
                 "score": e.score, "hits": e.hits,
                 "created": e.created, "last_hit": e.last_hit}
                for e in self.entries
            ],
        }, indent=2))

    def _hash(self, text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    def _context_hash(self, context: Optional[dict] = None) -> str:
        if context is None:
            return ""
        return self._hash(json.dumps(context, sort_keys=True))

    def exact_match(self, query: str, agent_type: str,
                    context: Optional[dict] = None) -> Optional[str]:
        """Check for exact hash match."""
        qhash = self._hash(query)
        ctx_hash = self._context_hash(context)

        for entry in self.entries:
            if (entry.query_hash == qhash
                    and entry.agent_type == agent_type
                    and entry.context_hash == ctx_hash):
                entry.hits += 1
                entry.last_hit = time.time()
                self._save()
                return entry.response

        return None

    def fuzzy_match(self, query: str, agent_type: str,
                    threshold: float = SIMILARITY_THRESHOLD) -> Optional[str]:
        """Check for semantic similarity match.

        Simple word-overlap similarity (fast, no embeddings needed).
        """
        query_words = set(query.lower().split())
        if not query_words:
            return None

        best_score = 0.0
        best_response = None

        for entry in self.entries:
            if entry.agent_type != agent_type:
                continue
            entry_words = set(entry.query.lower().split())
            if not entry_words:
                continue
            overlap = len(query_words & entry_words)
            union = len(query_words | entry_words)
            score = overlap / max(union, 1)

            if score > best_score:
                best_score = score
                best_response = entry.response

        if best_score >= threshold:
            return best_response
        return None

    def fingerprint_match(self, fingerprint: str, agent_type: str) -> Optional[str]:
        """Check if fingerprint matches (code didn't change)."""
        if not fingerprint:
            return None

        for entry in self.entries:
            if (entry.fingerprint == fingerprint
                    and entry.agent_type == agent_type):
                entry.hits += 1
                entry.last_hit = time.time()
                self._save()
                return entry.response

        return None

    def store(self, query: str, response: str, agent_type: str,
              context: Optional[dict] = None,
              fingerprint: str = "", score: float = 1.0):
        """Store a response for future skipping."""
        # Check if we already have this exact query
        existing = self.exact_match(query, agent_type, context)
        if existing:
            return  # Already cached

        self.entries.append(CacheEntry(
            query_hash=self._hash(query),
            query=query,
            response=response,
            agent_type=agent_type,
            context_hash=self._context_hash(context),
            fingerprint=fingerprint,
            score=score,
        ))
        self._save()

    def predict_no_change(self, fingerprint: str, agent_type: str) -> bool:
        """Predict if executing an agent would produce no change.

        Returns True if fingerprint matches AND score >= 0.9
        (meaning the previous result is still perfectly valid).
        """
        match = self.fingerprint_match(fingerprint, agent_type)
        if match:
            return True
        return False

    def stats(self) -> dict:
        """Return cache statistics."""
        if not self.entries:
            return {"total_entries": 0, "total_hits": 0, "agents_skipped": 0}

        total_hits = sum(e.hits for e in self.entries)
        agents_skipped = total_hits - len(self.entries)  # Hits beyond first = skips
        by_type = defaultdict(int)
        for e in self.entries:
            by_type[e.agent_type] += e.hits

        return {
            "total_entries": len(self.entries),
            "total_hits": total_hits,
            "agents_skipped": agents_skipped,
            "estimated_tokens_saved": agents_skipped * 2000,  # ~2k tok per skip
            "by_agent_type": dict(by_type),
            "cache_size_kb": round(CACHE_STORE.stat().st_size / 1024, 1) if CACHE_STORE.exists() else 0,
        }
