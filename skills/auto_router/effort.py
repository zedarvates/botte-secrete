"""Effort estimator — judge how much model muscle a task actually needs.

Turns a prompt (and optional task_type) into an effort score in [0,1] and a
target Tier. The router then maps that tier to the cheapest capable backend,
local first. This is the "auto decision effort": no manual tier picking.

Signals (cheap, deterministic, no LLM call):
  - explicit task_type (if given) seeds a base tier
  - length / expected output size
  - code blocks, stack traces, multi-file scope
  - reasoning vocabulary (design, prove, why, security, refactor across, …)
  - triviality vocabulary (classify, extract, list, rename, format, translate)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from skills.tiered_router import Tier, TASK_TIER


_REASON_WORDS = (
    "architecture", "design", "prove", "why", "trade-off", "tradeoff",
    "security", "audit", "vulnerab", "concurren", "race condition", "distributed",
    "refactor", "migrate", "optimize", "debug", "root cause", "algorithm",
    "threat model", "system design", "consistency", "deadlock",
)
_TRIVIAL_WORDS = (
    "classify", "categori", "extract", "list", "rename", "format", "translate",
    "summari", "spell", "lint", "tag", "label", "yes or no", "true or false",
    "one word", "in a word", "count",
)
_CODE_RE = re.compile(r"```|def |class |function |import |#include|=>|;\s*$", re.M)
_TRACE_RE = re.compile(
    r"traceback|stack trace|at [^\n(]{1,200}\([^()\n:]{1,200}:\d{1,10}\)|exception",
    re.I,
)
# crude multi-file signal: several path-like tokens
_PATH_RE = re.compile(r"(?:[\w-]+[./]){1,20}[a-zA-Z]{1,5}")


@dataclass
class EffortEstimate:
    score: float          # 0 (trivial) .. 1 (hardest)
    tier: Tier
    reasons: list[str]

    def to_dict(self) -> dict:
        return {"score": round(self.score, 3), "tier": self.tier.name,
                "reasons": self.reasons}


def estimate(prompt: str, task_type: str = "", expected_output: str = "") -> EffortEstimate:
    text = prompt.lower()
    reasons: list[str] = []
    score = 0.30  # neutral baseline → ~CHEAP

    # 1. explicit task_type seeds the score from the known tier map
    if task_type:
        seed = TASK_TIER.get(task_type)
        if seed is not None:
            score = {Tier.FREE: 0.0, Tier.LOCAL: 0.15, Tier.CHEAP: 0.4,
                     Tier.STANDARD: 0.65, Tier.PREMIUM: 0.9}[seed]
            reasons.append(f"task_type={task_type}→{seed.name}")

    reason_hits = sum(1 for w in _REASON_WORDS if w in text)

    words = len(prompt.split())
    if words > 400:
        score += 0.15; reasons.append("long prompt")
    elif words < 25 and reason_hits == 0:
        # Brevity only signals triviality when there's no reasoning vocabulary;
        # a terse "prove correctness under concurrency" is not a small task.
        score -= 0.10; reasons.append("short prompt")

    if reason_hits:
        score += min(0.40, 0.13 * reason_hits)
        reasons.append(f"reasoning vocab x{reason_hits}")

    trivial_hits = sum(1 for w in _TRIVIAL_WORDS if w in text)
    if trivial_hits:
        score -= min(0.30, 0.12 * trivial_hits)
        reasons.append(f"trivial vocab x{trivial_hits}")

    if _CODE_RE.search(prompt):
        score += 0.10; reasons.append("contains code")
    if _TRACE_RE.search(prompt):
        score += 0.15; reasons.append("stack trace / exception")

    paths = len(set(_PATH_RE.findall(prompt)))
    if paths >= 3:
        score += 0.12; reasons.append(f"multi-file scope ({paths} paths)")

    if expected_output and len(expected_output) > 400:
        score += 0.08; reasons.append("large expected output")

    score = round(max(0.0, min(1.0, score)), 3)  # round avoids float-boundary flips
    return EffortEstimate(score=score, tier=_tier_for(score), reasons=reasons)


# Default score→tier boundaries [free, local, cheap, standard]. The control loop
# (skills.control_loop) tunes these from measured outcomes; read live each call.
DEFAULT_THRESHOLDS = [0.08, 0.30, 0.55, 0.80]
_THRESHOLDS_PATH = __import__("pathlib").Path.home() / ".botte" / "routing-thresholds.json"


def load_thresholds() -> list:
    try:
        import json
        t = json.loads(_THRESHOLDS_PATH.read_text(encoding="utf-8")).get("thresholds")
        if isinstance(t, list) and len(t) == 4:
            return [float(x) for x in t]
    except (OSError, ValueError, TypeError):
        pass
    return list(DEFAULT_THRESHOLDS)


def _tier_for(score: float) -> Tier:
    free, local, cheap, standard = load_thresholds()
    if score < free:
        return Tier.FREE
    if score < local:
        return Tier.LOCAL
    if score < cheap:
        return Tier.CHEAP
    if score < standard:
        return Tier.STANDARD
    return Tier.PREMIUM
