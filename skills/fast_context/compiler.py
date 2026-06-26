"""compiler — compile les résultats d'exploration en rapport compact.

Formats de sortie:
    - compact: [{file:"path:line", snippet:"...", type:"import"}]
    - verbose: version détaillée avec score et contexte
    - markdown: pour affichage humain
"""

from __future__ import annotations

from typing import Optional


# Mapping des types de match
_SNIPPET_WIDTH = 80  # chars max d'un snippet


def _classify_match(match: dict) -> str:
    """Classifie le type de match (import, function, class, test, security, other)."""
    text = match.get("text", "")
    tl = text.lower()

    if tl.startswith("@pytest") or tl.startswith("def test_") or tl.startswith("def test"):
        return "test"
    if tl.startswith("import ") or tl.startswith("from "):
        return "import"
    if tl.startswith("async def ") or tl.startswith("def "):
        return "function"
    if tl.startswith("class "):
        return "class"
    if tl.startswith("@pytest") or tl.startswith("def test_") or tl.startswith("def test"):
        return "test"
    if any(w in tl for w in ("eval(", "exec(", "compile(", "shell=True",
                              "subprocess.run", "os.system(", "os.popen(")):
        return "security"
    if tl.startswith("#") or match.get("line_num", 0) <= 3:
        return "docstring"

    return "code"


def _truncate(text: str, width: int = _SNIPPET_WIDTH) -> str:
    """Tronque un texte à width chars, ajoute … si nécessaire."""
    if len(text) <= width:
        return text
    return text[:width - 1] + "…"


def compile_report(matches: list[dict], query: str,
                   max_results: int = 20) -> list[dict]:
    """Compile les matches en rapport compact.

    Chaque résultat:
        file: "chemin:ligne"
        snippet: texte tronqué à 80 chars
        type: import|function|class|test|security|docstring|code
        score: score de pertinence
    """
    seen: set = set()
    results = []
    for m in matches:
        key = (m.get("file", ""), m.get("line_num", 0))
        if key in seen:
            continue
        seen.add(key)

        results.append({
            "file": f"{m.get('file', '')}:{m.get('line_num', 0)}",
            "snippet": _truncate(m.get("text", "")),
            "type": _classify_match(m),
            "score": m.get("score", 0.0),
        })
        if len(results) >= max_results:
            break
    return results


def format_compact(matches: list[dict], query: str = "") -> str:
    """Formate en texte compact pour agent (0 token overhead).

    Format:
    ── main.py ──
    L15  import sqlite3                    [import .92]
    L42  def connect():                    [function .85]
    ── tests/test_main.py ──
    L3   def test_connect():               [test .78]
    """
    if not matches:
        return ""

    lines: list[str] = []
    current_file = ""
    m_count = 0

    for m in matches:
        file_label = m.get("file", "").rsplit(":", 1)[0] if ":" in m.get("file", "") else m.get("file", "")
        if file_label != current_file:
            current_file = file_label
            lines.append(f"── {current_file} ──")
        line = m.get("file", "").rsplit(":", 1)[-1] if ":" in m.get("file", "") else "?"
        snippet = m.get("snippet", "")
        mtype = m.get("type", "?")
        score = m.get("score", 0.0)
        lines.append(f"  L{line:<4} {snippet:<50} [{mtype} {score:.2f}]")
        m_count += 1

    if query:
        lines.insert(0, f"# FastContext: {query}")
        lines.insert(1, f"# {m_count} matches")

    return "\n".join(lines)


def format_markdown(matches: list[dict], query: str = "") -> str:
    """Formate en markdown pour affichage humain."""
    if not matches:
        return "*Aucun résultat trouvé.*"

    lines = [f"## 🔍 FastContext: {query}\n" if query else "## 🔍 FastContext\n"]
    current_file = ""
    buf: list[str] = []

    for m in matches:
        label = m.get("file", "")
        base = label.rsplit(":", 1)[0] if ":" in label else label
        line = label.rsplit(":", 1)[-1] if ":" in label else "?"

        if base != current_file:
            if buf:
                lines.extend(buf)
                buf = []
            current_file = base
            buf.append(f"\n### `{base}`\n")
            buf.append("|Ligne|Code|Type|Score|")
            buf.append("|----:|----|:--|:---:|")

        snippet = m.get("snippet", "").replace("`", "'")
        mtype = m.get("type", "?")
        score = m.get("score", 0.0)
        score_bar = "█" * int(score * 10) + "░" * (10 - int(score * 10))
        buf.append(f"|{line}|`{snippet}`|{mtype}|{score_bar} {score:.2f}|")

    if buf:
        lines.extend(buf)

    return "\n".join(lines)
