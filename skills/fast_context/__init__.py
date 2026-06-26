"""fast_context — exploration repo déterministe.

    from skills.fast_context import explore, cached_explore
    from skills.fast_context import discover_query_type, QueryType

    results = explore(".", "find DB connection patterns")
    # → [{"file": "src/db.py:15", "snippet": "...", "score": 0.92, ...}]

Pipeline par requête:
    1. discover_query_type(query) → QueryType
    2. readers dispatch selon type (glob/grep/read)
    3. ranker.score() chaque résultat
    4. compiler.compile() → rapport compact

Zéro dépendance LLM. Zéro token. ~5ms par exploration.
"""

from skills.fast_context.agent import explore, cached_explore, discover_query_type
from skills.fast_context.agent import QueryType

__all__ = [
    "explore", "cached_explore",
    "discover_query_type", "QueryType",
]
