"""Project metrics — the cost-focused numbers an audit should surface.

Aggregates the cheap/free signals into one report, broken down **per component**
(a project with a website + game server + client + tools has no single number),
and frames everything around token/cost:

  - LOC by language and by top-level component
  - duplicate-function groups (stdlib AST, free)
  - directive health + always-on context cost (CLAUDE.md tokens × turns)
  - local-routing posture (backends, % of work that can stay local)
  - skill-search cost avoided by find_skills
  - the audit's OWN cost (analysis ≈ 0 LLM tokens; only synthesis costs)

Optionally folds in a saved Porthos report (dead code / secrets) if present.
Pure stdlib.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional

# Reuse the scanner's ignore set so LOC counts match the deep scan.
try:
    from skills.fallow_like.scanner import DEFAULT_IGNORE_DIRS
except Exception:  # keep metrics usable even if fallow deps are missing
    DEFAULT_IGNORE_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules",
                           "dist", "build", ".kilo", ".kilocode", "worktrees",
                           "Archives", ".botte", ".pytest_cache", ".ruff_cache"}

# extension → (language, component-hint)
_EXT_LANG = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".vue": "Vue", ".svelte": "Svelte",
    ".zig": "Zig", ".rs": "Rust", ".go": "Go", ".java": "Java",
    ".c": "C", ".h": "C", ".cpp": "C++", ".hpp": "C++", ".cs": "C#",
    ".gd": "GDScript", ".cs ": "C#", ".gdshader": "Godot shader",
    ".html": "HTML", ".css": "CSS", ".scss": "CSS", ".sh": "Shell",
    ".lua": "Lua", ".rb": "Ruby", ".php": "PHP", ".kt": "Kotlin",
}

# Rough estimate of tokens to describe one skill when an agent reads the library.
_TOK_PER_SKILL = 150
# Assumed turns per agent session (for always-on context cost).
_TURNS_PER_SESSION = 30


@dataclass
class Metrics:
    project: str
    loc_total: int = 0
    files_total: int = 0
    by_language: dict = field(default_factory=dict)        # lang -> loc
    by_component: dict = field(default_factory=dict)       # top-dir -> {loc, langs}
    duplicate_groups: int = 0
    directive_score: int = 0
    always_on_tokens: int = 0
    skill_catalog: int = 0
    local_backends: list = field(default_factory=list)
    cloud_keys: list = field(default_factory=list)
    cost: dict = field(default_factory=dict)
    deep: dict = field(default_factory=dict)               # optional porthos summary

    def to_dict(self) -> dict:
        return asdict(self)


def _count_loc(project: Path):
    by_lang: dict[str, int] = {}
    by_comp: dict[str, dict] = {}
    total = files = 0
    for dirpath, dirnames, filenames in os.walk(project):
        dirnames[:] = [d for d in dirnames if d not in DEFAULT_IGNORE_DIRS]
        rel_parts = Path(dirpath).relative_to(project).parts
        comp = rel_parts[0] if rel_parts else "(root)"
        for fn in filenames:
            lang = _EXT_LANG.get(Path(fn).suffix.lower())
            if not lang:
                continue
            try:
                n = sum(1 for _ in open(Path(dirpath) / fn, "r", encoding="utf-8", errors="replace"))
            except OSError:
                continue
            total += n
            files += 1
            by_lang[lang] = by_lang.get(lang, 0) + n
            c = by_comp.setdefault(comp, {"loc": 0, "langs": {}})
            c["loc"] += n
            c["langs"][lang] = c["langs"].get(lang, 0) + n
    return total, files, by_lang, by_comp


def _load_porthos(project: Path) -> dict:
    """Pick up a saved Porthos report if one is reachable."""
    for cand in (project / ".botte" / "audit-report.json",
                 project / "audit-report.json"):
        if cand.exists():
            try:
                r = json.loads(cand.read_text(encoding="utf-8"))
                return {"health": r.get("h", {}), "by": r.get("by", {}),
                        "skipped": r.get("skipped", [])}
            except (json.JSONDecodeError, OSError):
                pass
    return {}


def collect(project: str | Path, porthos_report: Optional[Path] = None) -> Metrics:
    project = Path(project).resolve()
    m = Metrics(project=str(project))

    m.loc_total, m.files_total, m.by_language, m.by_component = _count_loc(project)

    # directives + always-on cost
    try:
        from skills.directives_audit import audit as dir_audit
        d = dir_audit(project)
        m.directive_score = d["score"]
        instr = [f for f in d["files"] if f["kind"] == "instructions"]
        m.always_on_tokens = sum(f["tokens_est"] for f in instr)
    except Exception:
        pass

    # duplication (free, stdlib)
    try:
        from skills.infra_advisor.auto_audit import duplication_scan
        m.duplicate_groups = duplication_scan(project)["duplicate_groups"]
    except Exception:
        pass

    # cluster posture
    try:
        from skills.llm_backends import registry
        m.local_backends = [f"{b.host}:{b.port}" for b in registry.chat_backends()]
    except Exception:
        pass
    m.cloud_keys = [k for k in ("OPENROUTER_API_KEY", "DEEPSEEK_API_KEY", "XAI_API_KEY",
                                "ZHIPUAI_API_KEY", "NVIDIA_API_KEY") if os.environ.get(k)]

    # skill catalog
    try:
        from skills.skill_finder import load_catalog
        m.skill_catalog = len(load_catalog())
    except Exception:
        pass

    if porthos_report and Path(porthos_report).exists():
        try:
            r = json.loads(Path(porthos_report).read_text(encoding="utf-8"))
            m.deep = {"health": r.get("h", {}), "by": r.get("by", {}),
                      "skipped": r.get("skipped", [])}
        except (json.JSONDecodeError, OSError):
            m.deep = {}
    else:
        m.deep = _load_porthos(project)

    m.cost = _cost_model(m)
    return m


def _cost_model(m: Metrics) -> dict:
    """Token/cost framing. Estimates, with the formulas made explicit."""
    always_on_per_session = m.always_on_tokens * _TURNS_PER_SESSION
    skill_search_saved = m.skill_catalog * _TOK_PER_SKILL
    local_capable = bool(m.local_backends)
    return {
        "analysis_llm_tokens": 0,            # the scans are deterministic Python
        "always_on_tokens_per_turn": m.always_on_tokens,
        "always_on_tokens_per_session": always_on_per_session,
        "always_on_note": f"{m.always_on_tokens} tok of instructions × ~{_TURNS_PER_SESSION} turns",
        "skill_search_tokens_avoided": skill_search_saved,
        "skill_search_note": f"{m.skill_catalog} skills × ~{_TOK_PER_SKILL} tok, avoided by find_skills",
        "local_routing_available": local_capable,
        "local_routing_note": ("cheap tasks (classification/extraction/summaries/"
                               "tool-search) can run at 0 cloud tokens"
                               if local_capable else
                               "no local backend — install LM Studio/Ollama to unlock"),
    }
