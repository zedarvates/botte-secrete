"""The built-in scripted scenario — 6 tasks that touch every filter of the
belt, so `demo --scripted` shows something real on a machine with no local
LLM installed and no network. Each step is a synthetic event, in the same
shape `skills.events.log_event` would produce.
"""

from __future__ import annotations

STEPS: list[dict] = [
    {
        "task": 'rename variable "a" to "count" in utils.py',
        "kind": "route", "filter": 1, "nn": "effort_classifier",
        "out": "local", "conf": 0.93, "tokens_saved": 210,
        "reason": "trivial edit, filter 1 (micro-NN) → local",
    },
    {
        "task": 'is this diff a bugfix or a feature? (git log message)',
        "kind": "route", "filter": 2, "nn": "-",
        "out": "local", "conf": 1.0, "tokens_saved": 150,
        "reason": "deterministic classifier — no model needed",
    },
    {
        "task": 'summarize this PR in 2 lines',
        "kind": "cache", "hit": True, "tokens_saved": 850,
        "reason": "identical prompt seen 4 minutes ago — cache hit",
    },
    {
        "task": 'design a distributed consensus protocol with a correctness proof',
        "kind": "route", "filter": 4, "nn": "-",
        "out": "cloud", "conf": None, "tokens_saved": 0,
        "reason": "genuinely hard reasoning — escalates to cloud (DeepSeek-R1)",
    },
    {
        "task": 'fix this failing test (local model drafted first)',
        "kind": "escalate", "from": "local", "to": "cloud",
        "reason": "verification_failed — local answer didn't pass the harness check",
    },
    {
        "task": 'error log spike at 03:14 — anomaly?',
        "kind": "nn_out", "model": "anomaly_detector",
        "probs": [0.04, 0.96], "label": "critical",
        "reason": "micro-NN flags critical, 0 tokens spent deciding",
    },
]


def totals(steps: list[dict]) -> dict:
    saved = sum(int(s.get("tokens_saved", 0)) for s in steps)
    cloud_calls = sum(1 for s in steps if s.get("out") == "cloud" or s.get("kind") == "escalate")
    cache_hits = sum(1 for s in steps if s.get("kind") == "cache" and s.get("hit"))
    return {"tokens_saved": saved, "cloud_calls": cloud_calls, "cache_hits": cache_hits}
