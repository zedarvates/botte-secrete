"""nlp_deterministic — classify & extract without an LLM (0 cloud tokens).

    from skills.nlp_deterministic import classify, extract_entities, keywords
    classify("speed up my SQL", {"perf": ["fast", "optimize", "slow"], "auth": ["login"]})
"""

from skills.nlp_deterministic.nlp import classify, extract_entities, keywords

__all__ = ["classify", "extract_entities", "keywords"]
