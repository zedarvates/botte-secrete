"""Advisory nearest-neighbour scribe. No model training, promotion or merging.

Lexical cosine is the dependency-free baseline. Supplied embeddings must use
the same model identity (including its revision) and dimension. Similarity is
never represented as a probability of correctness.
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter


def tokens(text):
    text = unicodedata.normalize("NFKD", text.casefold())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return Counter(re.findall(r"[\w.-]+", text))


def lexical_cosine(left, right):
    a, b = tokens(left), tokens(right)
    norm = math.sqrt(sum(v*v for v in a.values()) * sum(v*v for v in b.values()))
    return sum(v*b.get(k, 0) for k, v in a.items()) / norm if norm else 0.0


def vector_cosine(left, right):
    if left["model"] != right["model"] or len(left["vector"]) != len(right["vector"]):
        return None
    a, b = left["vector"], right["vector"]
    norm = math.hypot(*a) * math.hypot(*b)
    if not norm:
        return None
    return max(-1.0, min(1.0, sum(x*y for x, y in zip(a, b)) / norm))


def rank(query, candidates, embedding=None):
    """Reciprocal-rank fusion of nonzero lexical and matching vector results."""
    lexical, vector, exact = [], [], []
    for candidate in candidates:
        entry = candidate["entry"]
        text = entry.key + " " + entry.category + " " + candidate.get("search_text", candidate["text"])
        if query and query.strip().casefold() == entry.key.casefold():
            exact.append((1.0, entry.key))
        score = lexical_cosine(query, text) if query else 0.0
        if score > 0:
            lexical.append((score, entry.key))
        if embedding is not None and candidate.get("embedding") is not None:
            similarity = vector_cosine(embedding, candidate["embedding"])
            if similarity is not None and similarity > 0:
                vector.append((similarity, entry.key))
    scores = {}
    for channel, matches in (("exact", exact), ("lexical", lexical), ("vector", vector)):
        for position, (similarity, key) in enumerate(sorted(matches, key=lambda p: (-p[0], p[1])), 1):
            item = scores.setdefault(key, {"score": 0.0, "channels": {}})
            item["score"] += (3 if channel == "exact" else 1) / (60 + position)
            item["channels"][channel] = round(similarity, 6)
    if not query and embedding is None:
        scores = {c["entry"].key: {"score": 1 / (60+i), "channels": {"recent": True}}
                  for i, c in enumerate(candidates, 1)}
    return sorted(({**c, **scores[c["entry"].key]} for c in candidates
                   if c["entry"].key in scores), key=lambda c: (-c["score"], c["entry"].key))


def advise(record, candidates):
    nearest = rank(record["text"], candidates, record.get("embedding"))[:5]
    return {"mode": "advisory", "method": "knn_cosine_rrf",
            "declared_kind": record["kind"], "trained_micro_nn": False,
            "action": "review_neighbors" if nearest else "insufficient_neighbors",
            "neighbors": [{"key": c["entry"].key, "version": c["entry"].version,
                           "similarities": c["channels"]} for c in nearest],
            "mutated": False, "classification_verified": False,
            "note": "Similarity is not proof, a contradiction test, or permission to merge."}
