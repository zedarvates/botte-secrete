"""Trajectory Learning for Botte Secrète.

Stores optimization trajectories and searches similar past optimizations
to inform future decisions. Compatible with Hermes Trajectory Memory format.

Usage:
    from skills.trajectory import capture, search, stats
    tid = capture("bin_pack", {"items": [...], "capacity": 10}, result, latency=0.5)
    similar = search("pack 3 items into capacity 10")
"""

from __future__ import annotations

import json
import math
import re
import time
import hashlib
from pathlib import Path
from collections import Counter
from typing import Optional

from skills.trajectory.quality import (
    RouteAdvice,
    advise_route,
    embed_task,
    load_verified,
    quality_status,
    record_verified,
)
from skills.trajectory.outcome import emit_outcome, load_outcomes
from skills.trajectory.agent_run import emit_agent_run
from skills.trajectory.ci import emit_ci_outcome
from skills.trajectory.task_status import task_quality_status

TRAJECTORY_DIR = Path(__file__).parent / "store"
TRAJECTORY_FILE = TRAJECTORY_DIR / "trajectories.jsonl"
MAX_ENTRIES = 5000


def _ensure_dir():
    TRAJECTORY_DIR.mkdir(parents=True, exist_ok=True)
    if not TRAJECTORY_FILE.exists():
        TRAJECTORY_FILE.write_text("")


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zéèêëàâùûüôöîïç0-9]{3,}", text.lower())


def _trajectory_id(solver: str, task: str) -> str:
    raw = f"{solver}:{task}:{time.time()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def capture(
    solver: str,
    task: str,
    parameters: dict,
    result: Optional[dict] = None,
    error: Optional[str] = None,
    latency: Optional[float] = None,
    tokens_saved: Optional[int] = None,
) -> str:
    """Capture a solver trajectory.

    Args:
        solver: Solver name (assign_balanced, bin_pack, schedule, etc.)
        task: Task description
        parameters: Input parameters (items, workers, capacity, etc.)
        result: Solver output dict
        error: Error message if failed
        latency: Execution time in seconds
        tokens_saved: Estimated LLM tokens saved by using deterministic solver

    Returns:
        trajectory_id
    """
    _ensure_dir()

    entry = {
        "id": _trajectory_id(solver, task),
        "timestamp": time.time(),
        "datetime": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "solver": solver,
        "task": task,
        "parameters": parameters,
        "result": result,
        "error": error,
        "latency": latency,
        "tokens_saved": tokens_saved,
        "outcome": "success" if result and not error else "error" if error else "unknown",
    }

    with open(TRAJECTORY_FILE, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    _maybe_rotate()
    return entry["id"]


def _maybe_rotate():
    try:
        with open(TRAJECTORY_FILE) as f:
            lines = f.readlines()
        if len(lines) > MAX_ENTRIES:
            with open(TRAJECTORY_FILE, "w") as f:
                f.writelines(lines[-MAX_ENTRIES:])
    except OSError:
        pass


def load(limit: int = 1000) -> list[dict]:
    """Load trajectories, most recent first."""
    _ensure_dir()
    try:
        with open(TRAJECTORY_FILE) as f:
            lines = f.readlines()
    except OSError:
        return []

    entries = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
        if len(entries) >= limit:
            break
    return entries


def search(query: str, k: int = 3, min_score: float = 0.05,
           solver_filter: Optional[str] = None) -> list[dict]:
    """TF-IDF search for similar trajectories.

    Args:
        query: Search query (task description)
        k: Max results
        min_score: Minimum similarity score
        solver_filter: Filter by solver name

    Returns:
        [{trajectory: {...}, score: float}]
    """
    entries = load(limit=2000)
    if solver_filter:
        entries = [e for e in entries if e.get("solver") == solver_filter]
    if not entries:
        return []

    query_tokens = set(_tokenize(query))
    if not query_tokens:
        return []

    texts = [
        f"{e.get('task', '')} {e.get('solver', '')} "
        f"{' '.join(str(v) for v in e.get('parameters', {}).values())}"
        for e in entries
    ]

    def tfidf(text: str) -> float:
        tokens = _tokenize(text)
        if not tokens:
            return 0.0
        ct = Counter(tokens)
        score = 0.0
        for term in query_tokens:
            tf = ct.get(term, 0) / len(tokens)
            idf = math.log(len(texts) / max(sum(1 for t in texts if term in _tokenize(t)), 1))
            score += tf * idf
        return score / len(query_tokens)

    scored = []
    for i, entry in enumerate(entries):
        score = tfidf(texts[i])
        if score >= min_score:
            scored.append({"trajectory": entry, "score": round(score, 4)})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:k]


def get_stats() -> dict:
    """Statistics."""
    entries = load(limit=10000)
    if not entries:
        return {"total": 0}

    solvers = Counter(e.get("solver", "unknown") for e in entries)
    outcomes = Counter(e.get("outcome", "unknown") for e in entries)
    total_tokens = sum(e.get("tokens_saved", 0) or 0 for e in entries)
    avg_latency = sum(e.get("latency", 0) or 0 for e in entries) / len(entries)

    return {
        "total": len(entries),
        "solvers": dict(solvers),
        "outcomes": dict(outcomes),
        "total_tokens_saved": total_tokens,
        "avg_latency_sec": round(avg_latency, 3),
    }


__all__ = [
    "RouteAdvice",
    "advise_route",
    "capture",
    "embed_task",
    "emit_outcome",
    "emit_agent_run",
    "emit_ci_outcome",
    "task_quality_status",
    "get_stats",
    "load",
    "load_verified",
    "load_outcomes",
    "quality_status",
    "record_verified",
    "search",
]
