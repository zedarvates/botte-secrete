"""Form cache — detect similar prompts beyond exact match.

Extends ProjectCache with a lightweight similarity check (word Jaccard)
to catch prompts that are ~identical but not byte-exact.
"""

from __future__ import annotations

import hashlib
from typing import Optional


class FormCache:
    """Cache prompt forms (not exact text) for broader cache hits."""

    def __init__(self, threshold: float = 0.85):
        self.threshold = threshold
        self._cache: dict[str, str] = {}

    def _normalize(self, text: str) -> set[str]:
        """Normalize to word set for Jaccard comparison."""
        return set(text.lower().split())

    def _jaccard(self, a: set, b: set) -> float:
        if not a or not b:
            return 0.0
        return len(a & b) / len(a | b)

    def get(self, prompt: str) -> Optional[str]:
        words = self._normalize(prompt)
        for key, response in self._cache.items():
            cached_words = set(key.split("|"))
            if self._jaccard(words, cached_words) >= self.threshold:
                return response
        return None

    def set(self, prompt: str, response: str) -> None:
        key = "|".join(sorted(self._normalize(prompt)))
        self._cache[key] = response
