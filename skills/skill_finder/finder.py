"""Local skill/tool finder — pick the right skills for a task with 0 cloud tokens.

Finding which skill/tool/MCP fits a task is *retrieval*, not reasoning. So it
doesn't need a paid cloud model:

    Tier 0 (FREE, 0 tokens)  lexical + fuzzy match over each skill's
                             name / description / tags / triggers / body.
    Tier 1 (LOCAL, 0 cloud)  optionally, a local model re-ranks the shortlist
                             for genuinely ambiguous queries (skills.llm_backends).

The cloud model is then spent only on the actual work, not on picking tools.

Pure stdlib for Tier 0. Tier 1 reuses the local client when asked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional


REPO_ROOT = Path(__file__).resolve().parents[2]

_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "with", "my",
    "me", "i", "is", "are", "this", "that", "it", "how", "do", "can", "use",
    "using", "need", "want", "please", "help", "le", "la", "les", "un", "une",
    "de", "des", "du", "et", "ou", "pour", "dans", "avec", "mon", "ma", "mes",
    "je", "comment", "faire", "veux", "besoin",
}


@dataclass
class Skill:
    name: str
    path: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    tokens_est: int = 0
    _blob: str = field(default="", repr=False)  # lowercased searchable text

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("_blob", None)
        return d


@dataclass
class Match:
    skill: Skill
    score: float
    why: str

    def to_dict(self) -> dict:
        return {"name": self.skill.name, "score": round(self.score, 3),
                "why": self.why, "description": self.skill.description[:160],
                "path": self.skill.path, "tokens_est": self.skill.tokens_est}


# ── Catalog loading (robust to missing frontmatter) ──────────────────────────

def _parse_frontmatter(text: str) -> tuple[dict, str]:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.DOTALL)
    if not m:
        return {}, text
    fm_raw, body = m.group(1), m.group(2)
    fm: dict = {}
    for line in fm_raw.splitlines():
        if ":" in line and not line.startswith(" "):
            k, _, v = line.partition(":")
            fm[k.strip().lower()] = v.strip()
    return fm, body


def _summary_from_body(body: str) -> str:
    for line in body.splitlines():
        s = line.strip().lstrip("#").strip()
        if s and not s.startswith(("---", "```", "|")):
            return s[:240]
    return ""


def _split_list(val: str) -> list[str]:
    val = val.strip().strip("[]")
    return [t.strip().strip("'\"") for t in re.split(r"[,;]", val) if t.strip()]


def load_catalog(roots: Optional[list[Path]] = None) -> list[Skill]:
    """Find SKILL.md files under roots and build a searchable catalog.

    Defaults to this repo's skills/. Works whether or not a SKILL.md has
    YAML frontmatter — the full body is always indexed for matching.
    """
    roots = roots or [REPO_ROOT / "skills"]
    skills: list[Skill] = []
    seen: set[str] = set()
    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        for md in sorted(root.rglob("SKILL.md")):
            key = md.resolve().as_posix()
            if key in seen:
                continue
            seen.add(key)
            try:
                text = md.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            fm, body = _parse_frontmatter(text)
            name = fm.get("name") or md.parent.name
            desc = fm.get("description") or _summary_from_body(body)
            tags = _split_list(fm.get("tags", "")) if fm.get("tags") else []
            triggers = _split_list(fm.get("triggers", "")) if fm.get("triggers") else []
            blob = " ".join([name, desc, " ".join(tags), " ".join(triggers),
                             body]).lower()
            skills.append(Skill(
                name=name, path=md.relative_to(REPO_ROOT).as_posix() if md.is_relative_to(REPO_ROOT) else str(md),
                description=desc, tags=tags, triggers=triggers,
                tokens_est=max(1, len(text) // 4), _blob=blob,
            ))
    return skills


# ── Tier 0: lexical ranking (free) ───────────────────────────────────────────

def _tokens(text: str) -> list[str]:
    return [w for w in re.split(r"[^a-z0-9]+", text.lower()) if w and w not in _STOP and len(w) > 1]


def _fuzzy_hit(word: str, field_words: list[str]) -> float:
    best = 0.0
    for fw in field_words:
        if word == fw:
            return 1.0
        if len(word) >= 4 and (word in fw or fw in word):
            best = max(best, 0.8)
        else:
            r = SequenceMatcher(None, word, fw).ratio()
            if r >= 0.85:
                best = max(best, r)
    return best


def rank(query: str, catalog: Optional[list[Skill]] = None,
         top_k: int = 5, threshold: float = 0.08) -> list[Match]:
    """Score every skill against the query lexically. 0 tokens. Highest first."""
    catalog = catalog if catalog is not None else load_catalog()
    qwords = _tokens(query)
    if not qwords:
        return []

    matches: list[Match] = []
    for sk in catalog:
        name_words = _tokens(sk.name)
        strong_words = name_words + _tokens(" ".join(sk.tags + sk.triggers))
        desc_words = _tokens(sk.description)

        hit_terms: list[str] = []
        score = 0.0
        for w in qwords:
            s_strong = _fuzzy_hit(w, strong_words)        # name/tags/triggers: weight 3
            s_desc = _fuzzy_hit(w, desc_words)            # description: weight 1.5
            s_body = 1.0 if (len(w) > 2 and w in sk._blob) else 0.0  # body: weight 0.5
            best = max(s_strong * 3.0, s_desc * 1.5, s_body * 0.5)
            if best > 0:
                score += best
                if s_strong or s_desc:
                    hit_terms.append(w)
        if not score:
            continue
        # Normalise by query length so longer queries don't inflate scores.
        norm = score / (len(qwords) * 3.0)
        if norm >= threshold:
            if hit_terms:
                why = "matched: " + ", ".join(list(dict.fromkeys(hit_terms))[:6])
            else:
                why = "body keyword match"
            matches.append(Match(skill=sk, score=norm, why=why))

    matches.sort(key=lambda m: m.score, reverse=True)
    return matches[:top_k]


# ── Tier 1: optional local-LLM rerank (0 cloud tokens) ───────────────────────

def local_rerank(query: str, shortlist: list[Match],
                 max_tokens: int = 200) -> Optional[list[str]]:
    """Ask a LOCAL model to pick the relevant skills from a shortlist.

    Returns an ordered list of skill names, or None if no local backend / parse
    failure (caller then keeps the lexical order). Never calls the cloud.
    """
    try:
        from skills.llm_backends.client import LocalLLMClient, LocalLLMError
        from skills.llm_backends import registry
    except ImportError:
        return None
    if not registry.best_chat_backend() or not shortlist:
        return None

    listing = "\n".join(f"{i+1}. {m.skill.name}: {m.skill.description[:120]}"
                        for i, m in enumerate(shortlist))
    prompt = (
        "From the skills below, list ONLY the numbers relevant to the task, "
        "most relevant first, comma-separated (e.g. 3,1). No prose.\n\n"
        f"Task: {query}\n\nSkills:\n{listing}\n\nAnswer:")
    try:
        out = LocalLLMClient().chat(prompt, max_tokens=max_tokens, temperature=0.0).text
    except LocalLLMError:
        return None

    nums = [int(n) for n in re.findall(r"\d+", out) if 1 <= int(n) <= len(shortlist)]
    if not nums:
        return None
    ordered, seen = [], set()
    for n in nums:
        if n not in seen:
            seen.add(n)
            ordered.append(shortlist[n - 1].skill.name)
    return ordered


# ── Top-level ─────────────────────────────────────────────────────────────────

def find(query: str, roots: Optional[list[Path]] = None, top_k: int = 5,
         use_local: bool = False) -> dict:
    """Find the skills/tools relevant to a task. Free by default."""
    catalog = load_catalog(roots)
    matches = rank(query, catalog, top_k=top_k)
    result = {
        "query": query, "catalog_size": len(catalog),
        "tier": "free-lexical", "cloud_tokens": 0,
        "matches": [m.to_dict() for m in matches],
    }
    if use_local and matches:
        order = local_rerank(query, matches)
        if order:
            rankmap = {name: i for i, name in enumerate(order)}
            matches.sort(key=lambda m: rankmap.get(m.skill.name, 999))
            result["tier"] = "local-llm-reranked"
            result["matches"] = [m.to_dict() for m in matches]
    return result
