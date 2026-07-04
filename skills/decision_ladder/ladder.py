"""
Decision Ladder — Ponytail-inspired YAGNI enforcement.

Before writing ANY code, climb this ladder. Each rung that passes saves
the cost of every rung above it. The best code is the code you don't write.

Usage:
    from skills.decision_ladder.ladder import climb
    decision = climb("extract function names from a Python file")
    # → {rung: "stdlib", solution: "ast.parse() + ast.walk()", saved_lines: 15}
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class Rung:
    """One step on the decision ladder."""
    name: str
    description: str
    check: str = ""  # what this rung checks
    example: str = ""  # concrete example of passing


LADDER: list[Rung] = [
    Rung("stdlib", "Python standard library already does this",
         "Check if stdlib module handles this directly (os, pathlib, json, re, ast, sqlite3, http, etc.)",
         "extract function names → ast.parse() + ast.walk()"),
    Rung("regex_oneliner", "A regex, string method, or one-liner suffices",
         "Can a single re.sub / str.replace / list comprehension do it? No function needed.",
         "strip HTML tags → re.sub(r'<[^>]+>', '', text)"),
    Rung("existing_module", "An existing skill or module already covers this",
         "Check botte-secrete skills/ directory. Reuse > rebuild.",
         "code audit → skills/fallow_like/ already handles dead code detection"),
    Rung("new_code", "New code is genuinely needed — proceed",
         "No simpler alternative exists. Write the minimal implementation.",
         "custom OR-Tools solver for a novel scheduling constraint"),
]


@dataclass(slots=True)
class LadderResult:
    """Result of climbing the decision ladder."""
    task: str
    rung: str  # which rung was reached
    solution: str = ""  # suggested approach
    saved_lines: int = 0  # estimated lines avoided
    confidence: float = 0.0  # 0-1 how confident the suggestion is
    alternatives: list[str] = field(default_factory=list)


def _check_stdlib(task: str) -> str | None:
    """Check if a stdlib module can handle this task directly."""
    task_lower = task.lower()

    patterns = [
        (r"(json|parse.*json|read.*json|write.*json)", "json module (json.load/dump)"),
        (r"(csv|tsv|read.*csv|write.*csv|parse.*csv)", "csv module (csv.reader/writer)"),
        (r"(regex|pattern|match|extract.*text|find.*pattern)", "re module (re.search/sub/findall)"),
        (r"(file.*path|directory|folder|list.*files|find.*files|walk)", "pathlib.Path (iterdir/rglob) or os.walk"),
        (r"(http|fetch|download|api.*call|request)", "urllib.request (urlopen) or http.server"),
        (r"(sql|database|query|sqlite)", "sqlite3 module (stdlib, WAL mode)"),
        (r"(hash|sha|md5|checksum)", "hashlib module (stdlib)"),
        (r"(date|time|timestamp|schedule)", "datetime module (stdlib)"),
        (r"(ast|parse.*python|extract.*function|extract.*class|extract.*import)", "ast module (ast.parse/walk)"),
        (r"(config|ini|toml|settings.*file)", "tomllib (Python 3.11+) or configparser"),
        (r"(zip|tar|compress|archive|extract)", "zipfile or tarfile (stdlib)"),
        (r"(log|logging|debug.*output)", "logging module (stdlib)"),
        (r"(argparse|cli|command.*line|argument)", "argparse module (stdlib)"),
    ]

    for pattern, module in patterns:
        if re.search(pattern, task_lower):
            return module
    return None


def _check_regex_oneliner(task: str) -> str | None:
    """Check if this is a simple text transformation doable in one line."""
    task_lower = task.lower()

    patterns = [
        (r"(strip|remove).*html.*tag", "re.sub(r'<[^>]+>', '', text)"),
        (r"(strip|remove).*whitespace|trim|clean.*space", "text.strip() or ' '.join(text.split())"),
        (r"(count|frequency).*word|word.*count|word.*freq", "collections.Counter(words)"),
        (r"(split|tokenize).*text|split.*line", "text.split() or text.splitlines()"),
        (r"(extract|find).*email", "re.findall(r'[\\w.+-]+@[\\w-]+\\.[\\w.-]+', text)"),
        (r"(extract|find).*url", "re.findall(r'https?://[^\\s]+', text)"),
        (r"(replace|substitute).*string", "text.replace(old, new) or re.sub"),
        (r"(sort|order|rank).*list", "sorted(items, key=...)"),
        (r"(filter|select).*list|find.*all.*matching", "[x for x in items if condition(x)]"),
        (r"(unique|dedup|remove.*duplicate)", "list(set(items)) or list(dict.fromkeys(items))"),
    ]

    for pattern, solution in patterns:
        if re.search(pattern, task_lower):
            return solution
    return None


def _check_existing_module(task: str, skills_dir: Path | None = None) -> str | None:
    """Check if an existing botte skill already handles this."""
    if skills_dir is None:
        skills_dir = Path(__file__).resolve().parent.parent

    task_lower = task.lower()

    module_map = {
        r"(audit|dead.code|duplication|complexity|secrets|boundaries|code.quality)": "skills/fallow_like/",
        r"(fix|auto.*fix|repair|correct)": "skills/fix/",
        r"(security|vuln|taint|cwe|scan)": "skills/security_scanner/",
        r"(route|routing|effort|tier|escalat)": "skills/auto_router/",
        r"(local.*llm|ollama|lm.studio|harness)": "skills/local_harness/",
        r"(context|token.*count|token.*budget|prefix)": "skills/context_profiler/ / context_budget/",
        r"(mcp|server|gateway|tool.*expos)": "skills/mcp_gateway/ / llm_mcp/",
        r"(test|pytest|coverage|e2e)": "skills/app_test/",
        r"(doc|readme|document|changelog)": "skills/docs_steward/ / docgen/",
        r"(plan|planning|spec|design|architect)": "skills/writing-plans is loaded by Hermes, not botte directly",
        r"(control|ledger|adapt|threshold)": "skills/control_loop/",
        r"(red.team|adversarial|cardinal|mousquetaire)": "skills/cardinal/ / mousquetaires/",
    }

    for pattern, module_path in module_map.items():
        if re.search(pattern, task_lower):
            # module_path is like "skills/fallow_like/", strip "skills/" prefix
            clean_path = module_path.replace("skills/", "").split("/")[0]
            full_path = skills_dir / clean_path
            if full_path.exists():
                return module_path
    return None


def climb(task: str, skills_dir: Path | None = None) -> LadderResult:
    """Climb the decision ladder for a given task.

    Returns the highest (simplest) rung that can handle this task,
    or 'new_code' if no simpler alternative exists.
    """
    # Rung 1: stdlib
    stdlib = _check_stdlib(task)
    if stdlib:
        return LadderResult(
            task=task, rung="stdlib", solution=stdlib,
            saved_lines=15, confidence=0.85,
            alternatives=["Write a custom function instead — but stdlib is tested, documented, and free"]
        )

    # Rung 2: regex/one-liner
    oneliner = _check_regex_oneliner(task)
    if oneliner:
        return LadderResult(
            task=task, rung="regex_oneliner", solution=oneliner,
            saved_lines=10, confidence=0.80,
            alternatives=["Write a multi-line function — but this fits in one readable line"]
        )

    # Rung 3: existing module
    existing = _check_existing_module(task, skills_dir)
    if existing:
        return LadderResult(
            task=task, rung="existing_module", solution=f"Use {existing}",
            saved_lines=50, confidence=0.75,
            alternatives=["Rebuild from scratch — but the existing module is tested and maintained"]
        )

    # Rung 4: new code needed
    return LadderResult(
        task=task, rung="new_code",
        solution="No simpler alternative — proceed with minimal implementation",
        saved_lines=0, confidence=0.90,
        alternatives=[]
    )


def audit_task_list(tasks: list[str]) -> dict:
    """Audit a list of tasks and report how many could be avoided."""
    results = [climb(t) for t in tasks]
    by_rung: dict[str, int] = {}
    total_saved = 0
    for r in results:
        by_rung[r.rung] = by_rung.get(r.rung, 0) + 1
        total_saved += r.saved_lines

    return {
        "total_tasks": len(tasks),
        "new_code_needed": by_rung.get("new_code", 0),
        "avoidable": len(tasks) - by_rung.get("new_code", 0),
        "avoidable_pct": round((len(tasks) - by_rung.get("new_code", 0)) * 100 / max(len(tasks), 1)),
        "lines_saved": total_saved,
        "by_rung": by_rung,
        "details": [
            {"task": r.task, "rung": r.rung, "solution": r.solution[:80]}
            for r in results
        ],
    }
