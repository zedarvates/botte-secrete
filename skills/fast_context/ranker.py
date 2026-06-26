"""ranker — score chaque résultat de recherche par pertinence.

Score combiné (0.0 - 1.0):
    - proximité lexicale (0.0 - 0.5): overlaps query terms × position
    - rareté du fichier (0.0 - 0.25): extension, déjà vu ?
    - profondeur (0.0 - 0.25): plus le fichier est bas, moins pertinent
"""

from __future__ import annotations

import re
from pathlib import Path


# Mots de faible valeur sémantique (stop words)
_STOP_WORDS = frozenset({
    "the", "a", "an", "in", "on", "at", "to", "for", "of", "with",
    "and", "or", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would",
    "can", "could", "shall", "should", "may", "might", "must",
    "this", "that", "these", "those", "it", "its", "they", "them",
    "le", "la", "les", "un", "une", "des", "du", "de", "dans",
    "pour", "sur", "avec", "est", "sont", "pas",
})


def _tokenize(text: str) -> set[str]:
    """Tokenize un texte en mots-clés."""
    tokens = set(re.findall(r"[a-zA-Z_]\w{2,}", text.lower()))
    return tokens - _STOP_WORDS


def _query_type_weight(query: str, match_text: str) -> float:
    """Pondération selon le type de requête."""
    query_lower = query.lower()
    match_lower = match_text.lower()

    score = 0.0

    # Requête "import" → match exact des imports
    if "import" in query_lower or "dependency" in query_lower:
        if match_lower.startswith("import") or match_lower.startswith("from"):
            score += 0.3

    # Requête "function" → match de def
    if "function" in query_lower or "def " in query_lower or "method" in query_lower:
        if "def " in match_lower or "fn " in match_lower:
            score += 0.3

    # Requête "class" → match class
    if "class" in query_lower:
        if "class " in match_lower:
            score += 0.3

    # Requête "test" → match patterns test
    if "test" in query_lower:
        if "test" in match_lower or "assert " in match_lower:
            score += 0.2

    # Requête security → match pattern dangereux
    if any(w in query_lower for w in ("eval", "exec", "shell", "security", "audit")):
        if any(w in match_lower for w in ("eval(", "exec(", "shell=True", "subprocess")):
            score += 0.3

    return min(score, 0.5)


def _lexical_score(query_tokens: set[str], match_text: str, line_num: int) -> float:
    """Score basé sur le nombre de tokens de la requête qui apparaissent."""
    match_tokens = _tokenize(match_text)
    if not query_tokens:
        return 0.0

    overlaps = query_tokens & match_tokens
    ratio = len(overlaps) / len(query_tokens)

    # Bonus ligne 1 (docstring)
    position_bonus = 0.05 if line_num <= 3 else 0.0

    return min(ratio + position_bonus, 0.5)


def _depth_penalty(filepath: str) -> float:
    """Pénaliser les fichiers profondément imbriqués."""
    depth = Path(filepath).relative_to("/").parts.__len__() - 1 if filepath.startswith("/") else Path(filepath).parts.__len__()
    # > 6 niveaux → pénalité
    if depth > 6:
        return 0.1
    if depth > 4:
        return 0.2
    return 0.25


def _extension_bonus(filepath: str) -> float:
    """Bonus selon le type de fichier."""
    ext = Path(filepath).suffix.lower()
    bonuses = {
        ".py": 0.15,
        ".rs": 0.15,
        ".ts": 0.10,
        ".js": 0.10,
        ".md": 0.05,
        ".toml": 0.05,
        ".yaml": 0.05,
        ".yml": 0.05,
    }
    return bonuses.get(ext, 0.05)


def score(query: str, match_text: str, filepath: str, line_num: int) -> float:
    """Calcule un score de pertinence [0.0, 1.0]."""
    query_tokens = _tokenize(query)
    result = 0.0
    result += _query_type_weight(query, match_text)
    result += _lexical_score(query_tokens, match_text, line_num)
    result += _extension_bonus(filepath)
    result += _depth_penalty(filepath)
    return round(min(result, 1.0), 4)


def rank_results(matches: list[dict], query: str) -> list[dict]:
    """Classe les résultats par score décroissant, garde les meilleurs."""
    for m in matches:
        if "score" not in m:
            m["score"] = score(query, m.get("text", ""), m.get("file", ""), m.get("line_num", 0))
        m["score"] = round(m["score"], 4)

    ranked = sorted(matches, key=lambda x: (-x["score"], x.get("file", ""), x.get("line_num", 0)))
    return ranked
