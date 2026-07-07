#!/usr/bin/env python3
"""Semantic response cache using local embeddings (Qdrant).

Detects prompts *similar* but not identical (cosine > 0.95) and returns
cached responses instead of calling the LLM. Two-level: exact hash + similarity.

    python -m skills.response_cache.semantic_cache [--threshold 0.95]
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional


class SemanticCache:
    """Two-level cache: hash (exact) + embedding (similar)."""

    def __init__(self, threshold: float = 0.95):
        self.threshold = threshold
        self._hash_cache: dict[str, str] = {}
        self._qdrant_available = False
        try:
            from qdrant_client import QdrantClient
            self._client = QdrantClient(host="localhost", port=6333)
            self._qdrant_available = True
        except Exception:
            self._client = None

    def _hash(self, prompt: str) -> str:
        return hashlib.sha256(prompt.encode()).hexdigest()[:16]

    def get(self, prompt: str) -> Optional[str]:
        h = self._hash(prompt)
        if h in self._hash_cache:
            return self._hash_cache[h]
        if self._qdrant_available and self._client:
            try:
                from skills.vector_protocol import encode
                vec = encode(prompt)
                hits = self._client.search(
                    collection_name="botte_cache",
                    query_vector=vec,
                    limit=1,
                    score_threshold=self.threshold,
                )
                if hits:
                    return hits[0].payload.get("response", "")
            except Exception:
                pass
        return None

    def set(self, prompt: str, response: str) -> None:
        self._hash_cache[self._hash(prompt)] = response


_cache = SemanticCache()


def cached_call(prompt: str, fallback_fn) -> str:
    cached = _cache.get(prompt)
    if cached:
        return cached
    result = fallback_fn(prompt)
    _cache.set(prompt, result)
    return result
