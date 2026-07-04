"""Auto audit — one pass over the project where Botte Secrète is installed.

Combines the cheap, reliable checks into a single cost-focused report:

  - directives     CLAUDE.md / AGENTS.md health (directives_audit)
  - infra          hardware/software/MCP tips + ASCII cluster diagram (advisor)
  - duplication    duplicate function bodies across files (stdlib AST, free)
  - skills         size of the local skill catalog the agent can search for free

Plus pointers to the deeper, heavier passes (rtk, understand-anything, the full
fallow/mousquetaires pipeline) so the auto mode stays fast but tells you where to
go next. Pure stdlib.
"""

from __future__ import annotations

import ast
import hashlib
import re
from collections import defaultdict
from pathlib import Path
from typing import Optional

from skills.infra_advisor.advisor import advise

_SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".botte",
              "dist", "build", ".botte-cache",
              # duplicate working copies that inflate the dup count, not real dupes
              ".kilo", ".kilocode", "worktrees", "Archives", ".archive"}


def _norm(src: str) -> str:
    """Normalise a code block for duplicate detection (drop blanks/indent/comments)."""
    out = []
    for line in src.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        out.append(re.sub(r"\s+", " ", s))
    return "\n".join(out)


def duplication_scan(project: Path, min_lines: int = 5, top: int = 15) -> dict:
    """Find duplicate function/method bodies across the project's Python files."""
    buckets: dict[str, list] = defaultdict(list)
    files = 0
    for py in project.rglob("*.py"):
        if any(part in _SKIP_DIRS for part in py.parts):
            continue
        try:
            text = py.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(text)
        except (OSError, SyntaxError):
            continue
        files += 1
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                seg = ast.get_source_segment(text, node) or ""
                norm = _norm(seg)
                if norm.count("\n") + 1 < min_lines:
                    continue
                h = hashlib.sha256(norm.encode()).hexdigest()[:12]
                rel = py.relative_to(project).as_posix()
                buckets[h].append(f"{rel}:{node.lineno} {node.name}()")

    dups = [{"hash": h, "count": len(locs), "locations": locs[:6]}
            for h, locs in buckets.items() if len(locs) > 1]
    dups.sort(key=lambda d: d["count"], reverse=True)
    return {"python_files": files, "duplicate_groups": len(dups),
            "duplicates": dups[:top]}


_DEEPER = [
    "Code quality (dead code, complexity, secrets): "
    "python -m skills.mousquetaires.cli run <project>",
    "Per-project skill/token profile: "
    "python -m skills.skill_project_optimizer.cli optimize <project>",
    "Codebase knowledge graph: see skills/understand-anything/",
    "Compress command output in this repo's terminal: prefix commands with `botte` (rtk-style).",
]


def auto_audit(project: str | Path = ".", scan_subnet: bool = False) -> dict:
    project = Path(project).resolve()
    out: dict = {"project": str(project)}

    # directives
    try:
        from skills.directives_audit import audit as dir_audit
        d = dir_audit(project)
        out["directives"] = {"score": d["score"], "has_instructions": d["has_instructions"],
                             "findings": len(d["findings"])}
    except Exception as e:  # never let one sub-audit sink the whole report
        out["directives"] = {"error": str(e)}

    # infra advice (+ diagram)
    infra = advise(project=project, scan_subnet=scan_subnet)
    out["infra_score"] = infra["infra_score"]
    out["infra_tips"] = infra["tips"]
    out["diagram"] = infra["diagram"]

    # duplication
    try:
        out["duplication"] = duplication_scan(project)
    except Exception as e:
        out["duplication"] = {"error": str(e)}

    # local skill catalog
    try:
        from skills.skill_finder import load_catalog
        out["skill_catalog_size"] = len(load_catalog())
    except Exception:
        out["skill_catalog_size"] = 0

    # host skill catalog — estimate runtime overhead from Hermes
    try:
        from skills.context_profiler import profile_host
        hp = profile_host(str(project))
        out["host_prefix"] = {
            "total": hp["total_prefix_tokens"],
            "host_tokens": hp["breakdown"]["host"],
            "host_pct": hp["breakdown"]["host_pct"],
            "host_skill_catalog_tokens": hp["components"]["host_skill_catalog"],
            "host_skill_count": hp["counts"]["host_skills"],
            "reducible": hp["reducible_tokens"],
        }
        hsc = hp["components"]["host_skill_catalog"]
        if hsc > 5000:
            out.setdefault("infra_tips", []).append({
                "priority": "P1",
                "category": "infra",
                "title": f"Host skill catalog ~{hsc:,} tok ({hp['counts']['host_skills']} skills) — use lazy loading",
                "why": "The runtime injects all skill descriptions every turn. "
                       "This is the single largest source of token waste for any agent session.",
                "impact": f"Switch host to find_skills (keyword search): saves ~{hsc:,} tok/turn. "
                         "See `python -m skills.context_profiler.cli . --host` for full breakdown.",
            })
    except Exception:
        out["host_prefix"] = {"available": False}

    out["deeper_passes"] = _DEEPER
    out["headline"] = _headline(out)
    return out


def _headline(out: dict) -> str:
    bits = []
    d = out.get("directives", {})
    if "score" in d:
        bits.append(f"directives {d['score']}/100")
    bits.append(f"infra {out.get('infra_score','?')}/100")
    dup = out.get("duplication", {})
    if "duplicate_groups" in dup:
        bits.append(f"{dup['duplicate_groups']} duplicate-fn group(s)")
    return " · ".join(bits)
