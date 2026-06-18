#!/usr/bin/env python3
"""Tests for auto_router — decision logic offline, plus live local if a backend is up.

    python -m skills.auto_router.test_auto_router
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.tiered_router import Tier, Budget
from skills.auto_router import effort, providers
from skills.auto_router.router import AutoRouter
from skills.auto_router import fusion
from skills.llm_backends import registry


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def main() -> int:
    state = [0, 0]
    print("== auto_router tests ==")

    # 1. Effort estimator separates trivial from hard.
    trivial = effort.estimate("classify this ticket: bug or feature?")
    hard = effort.estimate(
        "Design a distributed rate limiter with consistency guarantees across "
        "nodes, analyse the trade-offs, and prove correctness under concurrency.")
    _ok("trivial task → low tier (FREE/LOCAL)", trivial.tier <= Tier.LOCAL, state)
    _ok("hard task → high tier (STANDARD/PREMIUM)", hard.tier >= Tier.STANDARD, state)
    _ok("hard effort score > trivial", hard.score > trivial.score, state)

    # 2. Provider catalog includes the requested models.
    keys = {m.key for m in providers.CATALOG}
    _ok("catalog has deepseek/glm/nemotron/grok/gemma",
        {"deepseek-chat", "glm", "nemotron", "grok", "gemma"} <= keys, state)

    # 3. Availability follows env keys.
    os.environ.pop("OPENROUTER_API_KEY", None)
    os.environ.pop("DEEPSEEK_API_KEY", None)
    _ok("no key → deepseek unavailable",
        not any(r.key == "deepseek-chat" for r in providers.available_cloud()), state)
    os.environ["OPENROUTER_API_KEY"] = "test-key"
    try:
        avail = {r.key for r in providers.available_cloud()}
        _ok("OPENROUTER key → cloud models available via openrouter",
            "deepseek-chat" in avail and
            providers.resolve(providers.CATALOG[1]).via == "openrouter", state)

        # 4. With cloud available, a hard task routes to cloud (decision only, no call).
        d = AutoRouter().decide(
            "Design a distributed system and prove correctness under concurrency "
            "with security analysis.", task_type="system_design")
        _ok("hard task + cloud key → mode=cloud", d.mode == "cloud", state)
        _ok("cloud decision carries a model slug", "/" in d.model, state)

        # 5. Native key preferred over OpenRouter.
        os.environ["DEEPSEEK_API_KEY"] = "native-key"
        r = providers.resolve(providers.CATALOG[1])  # deepseek-chat
        _ok("native key preferred over openrouter", r.via == "native", state)
    finally:
        os.environ.pop("OPENROUTER_API_KEY", None)
        os.environ.pop("DEEPSEEK_API_KEY", None)

    # 6. Trivial task always prefers local when a backend exists.
    if registry.best_chat_backend():
        d = AutoRouter().decide("classify: bug or feature?")
        _ok("trivial task → local backend", d.mode == "local", state)
    else:
        _ok("trivial task → none (no backend, offline)",
            AutoRouter().decide("hi").mode in ("local", "none"), state)

    # 7. No backend at all → mode none (budget=0 cloud, no local).
    saved = registry.best_chat_backend
    registry.best_chat_backend = lambda *a, **k: None  # type: ignore
    try:
        d = AutoRouter().decide("anything")
        _ok("no local + no cloud → mode=none", d.mode == "none", state)
    finally:
        registry.best_chat_backend = saved  # type: ignore

    # 8. Live: vote over local backend (if up) returns an answer.
    if registry.best_chat_backend():
        res = fusion.vote("Capital of France, one word only.", max_tokens=24)
        _ok(f"live vote returns answer ({res.get('total',0)} ballot(s))",
            bool(res.get("answer")), state)
    else:
        print("  [skip] live vote — no backend")

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
