"""skill_finder — pick the right skills/tools for a task locally (0 cloud tokens).

    from skills.skill_finder import find
    find("optimize slow postgres queries")          # free lexical match
    find("set up an A/B test", use_local=True)       # local-LLM rerank, 0 cloud

Retrieval, not reasoning — so a paid cloud model never needs to do skill search.
"""

from skills.skill_finder.finder import (
    find, rank, load_catalog, local_rerank, Skill, Match,
)

__all__ = ["find", "rank", "load_catalog", "local_rerank", "Skill", "Match"]
