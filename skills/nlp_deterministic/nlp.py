"""Deterministic NLP — classify and extract WITHOUT an LLM.

Many "ask the model to classify / extract" calls don't need a model at all: a
rule + gazetteer + local-embedding pass is deterministic, instant, and **0 cloud
tokens**. This is the NLP half of the determinism program (alongside the
combinatorial solvers): replace LLM reasoning for structured language decisions
with exact, repeatable computation.

  classify(text, intents)    intent classification: lexical overlap + a local
                             hash-embedding cosine signal (deterministic).
  extract_entities(text)     regex/gazetteer extraction (urls, emails, ips,
                             paths, env vars, flags, numbers).
  keywords(text)             stopword-filtered keyphrase frequency.

Pure stdlib; reuses the local hash embedding ([[ingest]]) and cosine
([[vector_protocol]]) — both work offline with no model.
"""

from __future__ import annotations

import re
from typing import Optional

_WORD = re.compile(r"[a-z0-9]+")

# Small English + French stopword set — enough to denoise keyword extraction.
_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "is",
    "are", "be", "this", "that", "it", "as", "at", "by", "from", "my", "your",
    "i", "you", "we", "they", "do", "does", "how", "what", "can", "should",
    "le", "la", "les", "un", "une", "de", "des", "du", "et", "ou", "à", "en",
    "dans", "sur", "pour", "avec", "est", "ce", "cette", "mon", "ma", "mes",
    "je", "tu", "il", "elle", "que", "qui", "plus", "pas", "ne",
}


def _tokens(text: str) -> list:
    return _WORD.findall((text or "").lower())


# ── intent classification ────────────────────────────────────────────────────

def classify(text: str, intents: dict, *, use_embed: bool = True,
             lex_weight: float = 0.7) -> dict:
    """Classify text into one of ``intents`` = {label: [keywords/phrases]}.

    Score = lexical keyword recall (how many of an intent's keywords appear)
    blended with a local hash-embedding cosine. Deterministic, 0 cloud tokens.
    Returns {label, score, scores, cloud_tokens}.
    """
    text = (text or "").strip()
    if not text or not intents:
        return {"label": None, "score": 0.0, "scores": {}, "cloud_tokens": 0}

    qset = set(_tokens(text))
    emb_fn = cos = None
    if use_embed:
        try:
            from skills.ingest.ingest import _hash_embed
            from skills.vector_protocol import cosine_similarity
            emb_fn, cos = _hash_embed, cosine_similarity
        except Exception:
            emb_fn = cos = None

    qvec = emb_fn(text) if emb_fn else None
    scores: dict = {}
    for label, kws in intents.items():
        kw_text = " ".join(kws) if isinstance(kws, (list, tuple)) else str(kws)
        kwset = set(_tokens(kw_text))
        lex = len(qset & kwset) / len(kwset) if kwset else 0.0
        emb = 0.0
        if emb_fn and cos and kw_text.strip():
            emb = max(0.0, cos(qvec, emb_fn(kw_text)))
        scores[label] = round(lex_weight * lex + (1 - lex_weight) * emb, 4)

    best = max(scores, key=scores.get)
    return {"label": best, "score": scores[best], "scores": scores,
            "cloud_tokens": 0}


# ── entity extraction (regex + gazetteers) ───────────────────────────────────

_PATTERNS = {
    "urls": re.compile(r"https?://[^\s)>\]\"']+"),
    "emails": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "ips": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b"),
    "env_vars": re.compile(r"\$\{?[A-Z_][A-Z0-9_]*\}?|%[A-Z_][A-Z0-9_]*%"),
    "flags": re.compile(r"(?<!\S)--?[A-Za-z][A-Za-z0-9-]+"),
    "paths": re.compile(r"(?<!\S)(?:[A-Za-z]:\\|\.{0,2}/)[^\s:?*\"<>|]+"),
    "numbers": re.compile(r"(?<!\w)-?\d+(?:\.\d+)?(?!\w)"),
}


def extract_entities(text: str) -> dict:
    """Pull common entities out of text with regexes. Deterministic, 0 tokens."""
    text = text or ""
    out: dict = {}
    for name, pat in _PATTERNS.items():
        seen, vals = set(), []
        for m in pat.finditer(text):
            v = m.group(0)
            if v not in seen:
                seen.add(v)
                vals.append(v)
        out[name] = vals
    out["cloud_tokens"] = 0
    return out


# ── keyword extraction ───────────────────────────────────────────────────────

def keywords(text: str, *, top_k: int = 8, min_len: int = 3) -> dict:
    """Stopword-filtered keyword frequency. Deterministic, 0 tokens."""
    from collections import Counter
    counts = Counter(w for w in _tokens(text)
                     if len(w) >= min_len and w not in _STOP)
    top = counts.most_common(top_k)
    return {"keywords": [{"word": w, "count": c} for w, c in top],
            "cloud_tokens": 0}
