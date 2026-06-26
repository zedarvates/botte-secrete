"""store — cache LRU simple pour les résultats d'exploration.

Évite de rescanner les mêmes fichiers dans une session courte.
TTL configurable (défaut: 30 secondes).
Utilise collections.OrderedDict (stdlib).
"""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any, Optional


class LRUCache:
    """Cache LRU avec TTL.

    Usage:
        cache = LRUCache(maxsize=64, ttl=30)
        cache.put("path:query", results)
        cached = cache.get("path:query")  # → None si expiré
    """

    def __init__(self, maxsize: int = 64, ttl: float = 30.0):
        self._maxsize = maxsize
        self._ttl = ttl
        self._store: OrderedDict = OrderedDict()
        self._timestamps: dict = {}

    def put(self, key: str, value: Any) -> None:
        """Stocke une valeur avec timestamp."""
        self._store[key] = value
        self._timestamps[key] = time.monotonic()
        self._store.move_to_end(key)
        self._evict()

    def get(self, key: str) -> Optional[Any]:
        """Retourne la valeur si valide, None si expiré ou absent."""
        if key not in self._store:
            return None
        ts = self._timestamps.get(key, 0)
        if time.monotonic() - ts > self._ttl:
            self._remove(key)
            return None
        self._store.move_to_end(key)
        return self._store[key]

    def invalidate(self, key: Optional[str] = None) -> None:
        """Invalide une clé ou tout le cache."""
        if key:
            self._remove(key)
        else:
            self._store.clear()
            self._timestamps.clear()

    def _remove(self, key: str) -> None:
        self._store.pop(key, None)
        self._timestamps.pop(key, None)

    def _evict(self) -> None:
        while len(self._store) > self._maxsize:
            self._store.popitem(last=False)

    @property
    def size(self) -> int:
        return len(self._store)

    @property
    def keys(self) -> list[str]:
        return list(self._store.keys())


# Cache global par défaut
_default_cache = LRUCache(maxsize=64, ttl=30.0)


def default_cache() -> LRUCache:
    return _default_cache
