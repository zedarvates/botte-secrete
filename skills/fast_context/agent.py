"""agent — FastContext orchestrateur d'exploration.

Pipeline:
    1. discover_query_type(query) → QueryType
    2. readers dispatch selon type
    3a. IMPORTS → grep import/from → rank
    3b. FUNCTION → grep def → file context → rank
    3c. TESTS → glob test_* → grep → rank
    3d. PATTERN → grep générique → rank
    3e. SECURITY → grep patterns dangereux → rank
    4. compiler.compile_report() → rapport list[dict]
"""

from __future__ import annotations

import enum
from pathlib import Path
from typing import Optional

from skills.fast_context.readers import fast_read, fast_glob, fast_grep, get_file_stats
from skills.fast_context.ranker import rank_results
from skills.fast_context.compiler import compile_report
from skills.fast_context.store import default_cache


class QueryType(enum.Enum):
    """Type de requête d'exploration."""
    IMPORTS = "imports"
    FUNCTION = "function"
    TESTS = "tests"
    PATTERN = "pattern"
    SECURITY = "security"
    UNKNOWN = "unknown"


# Mots-clés par type de requête
_QUERY_SIGNATURES: list[tuple[set[str], QueryType]] = [
    ({"import", "dependency", "depend", "package", "library", "module"}, QueryType.IMPORTS),
    ({"function", "method", "def ", "definition", "understand", "what does", "how does"}, QueryType.FUNCTION),
    ({"test", "spec", "unittest", "pytest", "assert"}, QueryType.TESTS),
    ({"security", "audit", "eval", "exec", "shell", "malicious", "dangerous",
      "vulnerability", "backdoor", "exploit", "hack"}, QueryType.SECURITY),
    ({"pattern", "usage", "find", "where", "search", "look", "show me"}, QueryType.PATTERN),
]


def discover_query_type(query: str) -> QueryType:
    """Détermine le type de requête à partir de mots-clés."""
    ql = query.lower()
    for keywords, qtype in _QUERY_SIGNATURES:
        if any(kw in ql for kw in keywords):
            return qtype
    return QueryType.PATTERN  # fallback


# ── Handlers par type ──


def _handle_imports(query: str, root: str, max_results: int) -> list[dict]:
    """Trouve les imports/dépendances dans le projet."""
    matches = []
    # grep pour les imports Python
    py_matches = fast_grep(r"^(import |from )", root, max_matches=max_results * 2)
    matches.extend(py_matches)
    if len(matches) < max_results:
        # grep pour les dépendances dans conf files
        toml_matches = fast_grep(r"^\[project\.dependencies\]", root, max_matches=5)
        matches.extend(toml_matches)
    return matches


def _handle_function(query: str, root: str, max_results: int) -> list[dict]:
    """Trouve les définitions de fonctions."""
    matches = fast_grep(r"(async )?(def |fn )", root, max_matches=max_results * 2)
    return matches


def _handle_tests(query: str, root: str, max_results: int) -> list[dict]:
    """Trouve les tests."""
    test_files = fast_glob("**/test_*.py", root)[:max_results]
    matches: list[dict] = []
    for tf in test_files:
        # grep pour les fonctions de test dans chaque fichier
        content = fast_read(tf)
        for i, line in enumerate(content, 1):
            if "def test_" in line or "def test" in line and "def" in line:
                matches.append({"file": tf, "line_num": i, "text": line.strip()})
    return matches


def _handle_pattern(query: str, root: str, max_results: int) -> list[dict]:
    """Recherche générique par pattern."""
    # Extraire le terme de recherche de la requête
    # Enlève les mots-clés de type
    ql = query.lower()
    for keywords, _ in _QUERY_SIGNATURES:
        for kw in keywords:
            ql = ql.replace(kw, "")
    # Garde les mots significatifs (≥ 3 chars)
    import re
    terms = [w for w in re.findall(r"[a-zA-Z_]\w{2,}", ql)
             if w not in {"find", "where", "search", "look", "show", "pattern", "usage"}]

    if not terms:
        # fallback: dernier mot de la requête
        words = query.split()
        terms = [words[-1]] if words else []

    # Chercher chaque terme
    matches: list[dict] = []
    seen: set = set()
    for term in terms[:3]:  # max 3 termes
        term_matches = fast_grep(re.escape(term), root, max_matches=max_results)
        for m in term_matches:
            key = (m["file"], m["line_num"])
            if key not in seen:
                seen.add(key)
                matches.append(m)
    return matches


def _handle_security(query: str, root: str, max_results: int) -> list[dict]:
    """Recherche des patterns de sécurité dangereux."""
    # Patterns multiples pour la sécurité
    dangerous_patterns = [
        (r"eval\s*\(", "eval"),
        (r"exec\s*\(", "exec"),
        (r"compile\s*\(", "compile"),
        (r"shell\s*=\s*True", "shell=True"),
        (r"os\.system\s*\(", "os.system"),
        (r"os\.popen\s*\(", "os.popen"),
        (r"subprocess\.(call|run|Popen)\s*\(", "subprocess"),
        (r"pickle\.loads\s*\(", "pickle.loads"),
        (r"base64\.(b64decode|decode)", "base64 decode"),
        (r"bytes\(\[.*\]\)\.decode", "obfuscated bytes"),
        (r"open\(.*[\"'][^\"']*[\"'].*,\s*[\"']w[\"']", "open write"),
    ]

    matches: list[dict] = []
    seen: set = set()
    for pattern, label in dangerous_patterns:
        term_matches = fast_grep(pattern, root, max_matches=10)
        for m in term_matches:
            m["_danger"] = label
            key = (m["file"], m["line_num"])
            if key not in seen:
                seen.add(key)
                matches.append(m)
        if len(matches) >= max_results:
            break
    return matches


# Dispatch table
_HANDLERS = {
    QueryType.IMPORTS: _handle_imports,
    QueryType.FUNCTION: _handle_function,
    QueryType.TESTS: _handle_tests,
    QueryType.PATTERN: _handle_pattern,
    QueryType.SECURITY: _handle_security,
}


def explore(root: str, query: str, max_results: int = 20) -> list[dict]:
    """Point d'entrée principal: explore le repo selon la requête.

    Args:
        root: Chemin du projet à explorer
        query: Requête en langage naturel
        max_results: Nombre max de résultats

    Returns:
        Liste de dicts: [{file, snippet, type, score}, ...]
    """
    qtype = discover_query_type(query)
    handler = _HANDLERS.get(qtype, _handle_pattern)

    raw = handler(query, root, max_results * 2)
    ranked = rank_results(raw, query)

    # Si c'est une requête security, ajoute le label de danger
    if qtype == QueryType.SECURITY:
        for m in ranked:
            label = m.pop("_danger", None)
            if label:
                m["danger"] = label

    report = compile_report(ranked, query, max_results=max_results)
    return report


def cached_explore(root: str, query: str, max_results: int = 20,
                   ttl: float = 30.0) -> list[dict]:
    """Exploration avec cache LRU (même requête = pas de rescann)."""
    cache = default_cache()
    key = f"{Path(root).resolve()}:{query.lower().strip()}:{max_results}"

    cached = cache.get(key)
    if cached is not None:
        return cached

    result = explore(root, query, max_results)
    cache.put(key, result)
    return result
