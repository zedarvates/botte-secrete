"""
Micro-NN Router — route tasks to the right micro-NN model based on complexity.

Tiers:
    nano (0-50 tokens)    → regex/deterministic rules
    micro (50-200 tokens) → distilled NN (fast, local)
    medium (200-500)      → full NN (higher accuracy)
    macro (500+)          → escalate to fallback LLM

Usage:
    from skills.nn_router.router import Router
    router = Router()
    tier, model = router.route("parse JSON config")
    # → ("nano", "rules")
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# Task complexity patterns
COMPLEXITY_PATTERNS = {
    "nano": [
        r"parse\s+(json|csv|config)",
        r"strip\s+(html|tags|whitespace)",
        r"count\s+\w+",
        r"\bregex\b|\bpattern\b|\bmatch\b",
        r"(?<!\w)format(?!\w)|pretty.?print",
        r"read\s+file|write\s+file",
        r"sort|filter|dedup|unique",
        r"lower\b|upper\b|trim\b|split\b|join\b",
        r"current\s+(time|date|timestamp)",
        r"hash|crc|checksum|md5|sha",
    ],
    "micro": [
        r"validate\s+\w+",
        r"extract\s+\w+",
        r"transform|convert\s+\w+",
        r"find\s+.*\s+in\s+\w+",
        r"check\s+(if|whether)\s+\w+",
        r"compare|diff|merge",
        r"simple\s+(classification|prediction)",
    ],
    "medium": [
        r"audit|analyze|review\s+code",
        r"detect|identify\s+pattern",
        r"classify\s+\w+",
        r"summarize|aggregate",
        r"complex\s+validation",
        r"multi.?step\s+transformation",
    ],
    "macro": [
        r"design|architect|plan",
        r"debug|troubleshoot",
        r"generate\s+(code|test|doc)",
        r"complex\s+(analysis|inference)",
        r"learn|adapt|optimize",
        r"escalate|review",
    ],
}

MODEL_TIERS = {
    "nano": {
        "name": "rules",
        "description": "Deterministic rules / regex",
        "latency_ms": 1,
        "cost": 0,
    },
    "micro": {
        "name": "qwen2:0.5b",
        "description": "Distilled nano-LLM via Ollama",
        "latency_ms": 50,
        "cost": 1,
    },
    "medium": {
        "name": "gemma-4-e2b",
        "description": "LocalAI gemma (4B parameters)",
        "latency_ms": 200,
        "cost": 3,
    },
    "macro": {
        "name": "deepseek-v4-flash",
        "description": "API-backed frontier model",
        "latency_ms": 500,
        "cost": 10,
    },
}


def estimate_complexity(task: str) -> int:
    """Estimate task complexity on a scale of 1-10."""
    task_lower = task.lower()
    score = 1

    # Length
    if len(task) > 100:
        score += 1
    if len(task) > 200:
        score += 1

    # Pattern matches
    for pattern in COMPLEXITY_PATTERNS["nano"]:
        if re.search(pattern, task_lower):
            return 1

    for pattern in COMPLEXITY_PATTERNS["micro"]:
        if re.search(pattern, task_lower):
            score = max(score, 2)

    for pattern in COMPLEXITY_PATTERNS["medium"]:
        if re.search(pattern, task_lower):
            score = max(score, 4)

    for pattern in COMPLEXITY_PATTERNS["macro"]:
        if re.search(pattern, task_lower):
            score = max(score, 7)

    return min(score, 10)


def route(task: str) -> tuple[str, str, int]:
    """Route a task to the appropriate tier.

    Returns:
        (tier_name, model_name, complexity_score)
    """
    score = estimate_complexity(task)

    if score <= 1:
        tier = "nano"
    elif score <= 3:
        tier = "micro"
    elif score <= 6:
        tier = "medium"
    else:
        tier = "macro"

    model_info = MODEL_TIERS[tier]
    return tier, model_info["name"], score


def batch_route(tasks: list[str]) -> list[dict]:
    """Route multiple tasks and return structured results."""
    results = []
    for task in tasks:
        tier, model, score = route(task)
        results.append({
            "task": task[:80],
            "tier": tier,
            "model": model,
            "complexity": score,
            "estimated_latency_ms": MODEL_TIERS[tier]["latency_ms"],
            "estimated_cost": MODEL_TIERS[tier]["cost"],
        })
    return results


def routing_stats(routes: list[dict]) -> dict:
    """Compute routing statistics."""
    from collections import Counter
    by_tier = Counter(r["tier"] for r in routes)
    total_cost = sum(r["estimated_cost"] for r in routes)
    avg_complexity = sum(r["complexity"] for r in routes) / max(len(routes), 1)
    return {
        "total_tasks": len(routes),
        "by_tier": dict(by_tier),
        "total_cost": total_cost,
        "avg_complexity": round(avg_complexity, 1),
    }