#!/usr/bin/env python3
"""Focused offline tests for the auto-router quality-outcome adapter."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from skills.auto_router import effort
from skills.auto_router import router as router_mod
from skills.auto_router.router import AutoDecision, AutoRouter
from skills.llm_backends.client import LocalLLMError
from skills.tiered_router import Tier
from skills.trajectory.outcome import load_outcomes
from skills.trajectory.quality import load_verified


def _ok(message: str, condition: bool, state: list[int]) -> None:
    print(f"  [{'PASS' if condition else 'FAIL'}] {message}")
    state[0 if condition else 1] += 1


def _decision(mode: str) -> AutoDecision:
    return AutoDecision(
        mode=mode,
        tier=Tier.LOCAL if mode != "cloud" else Tier.CHEAP,
        effort=effort.estimate("x"),
        model=f"{mode}-model" if mode != "none" else "",
        est_cost=0.001 if mode == "cloud" else 0.0,
    )


def main() -> int:
    state = [0, 0]
    print("== auto-router outcome adapter tests ==")

    from skills import response_cache as cache_mod

    original_decide = AutoRouter.decide
    original_client = router_mod.LocalLLMClient
    original_cloud = router_mod._cloud_chat
    original_cache_get = cache_mod._cache.get
    original_cache_set = cache_mod._cache.set
    cache_mod._cache.get = lambda *_args, **_kwargs: None
    cache_mod._cache.set = lambda *_args, **_kwargs: None

    class _Result:
        text = "backend returned text"
        total_tokens = 7

    class _Client:
        def chat(self, *_args, **_kwargs):
            return _Result()

    private_task = "route SECRET_ROUTER_CANARY_761 safely"
    private_execution = "router-run/private-761"
    try:
        with tempfile.TemporaryDirectory() as project:
            AutoRouter.decide = lambda self, *_args, **_kwargs: _decision("local")
            router_mod.LocalLLMClient = _Client
            first = AutoRouter().run(
                private_task, project_root=project, execution_id=private_execution,
                task_type="routing",
            )
            replay = AutoRouter().run(
                private_task, project_root=project, execution_id=private_execution,
                task_type="routing",
            )
            rows = load_outcomes(project)
            raw = (Path(project) / ".botte" / "quality-outcomes.jsonl").read_text(
                encoding="utf-8"
            )
            _ok("backend return emits unverified PARTIAL",
                len(rows) == 1 and rows[0]["status"] == "PARTIAL"
                and rows[0]["verification_state"] == "unverified"
                and first.get("outcome_id") == rows[0]["id"], state)
            _ok("stable execution replay is idempotent",
                replay.get("outcome_deduplicated") is True and len(rows) == 1, state)
            _ok("task and execution text stay private",
                "SECRET_ROUTER_CANARY_761" not in raw
                and private_execution not in raw, state)
            _ok("backend self-report creates no verified label",
                not load_verified(project), state)
            _ok("envelope preserves observed route, model, tokens, and authority",
                rows[0]["route"] == "local" and rows[0]["model"] == "local-model"
                and rows[0]["tokens"] == 7 and rows[0]["acted"] is True
                and rows[0]["shadow_only"] is True
                and rows[0]["activation_allowed"] is False, state)

        with tempfile.TemporaryDirectory() as project:
            AutoRouter.decide = lambda self, *_args, **_kwargs: _decision("none")
            result = AutoRouter().run(private_task, project_root=project)
            rows = load_outcomes(project)
            _ok("unavailable route emits ABSTAINED without acting",
                "error" in result and len(rows) == 1
                and rows[0]["status"] == "ABSTAINED"
                and rows[0]["abstained"] is True
                and rows[0]["acted"] is False, state)

        class _FailingClient:
            def chat(self, *_args, **_kwargs):
                raise LocalLLMError("offline test failure")

        with tempfile.TemporaryDirectory() as project:
            AutoRouter.decide = lambda self, *_args, **_kwargs: _decision("local")
            router_mod.LocalLLMClient = _FailingClient
            result = AutoRouter().run(private_task, project_root=project)
            rows = load_outcomes(project)
            _ok("local backend error emits an unverified FAIL",
                "error" in result and len(rows) == 1 and rows[0]["status"] == "FAIL"
                and rows[0]["verified"] is False, state)

        with tempfile.TemporaryDirectory() as project:
            AutoRouter.decide = lambda self, *_args, **_kwargs: _decision("cloud")
            router_mod._cloud_chat = lambda *_args, **_kwargs: (_ for _ in ()).throw(
                RuntimeError("offline cloud failure")
            )
            raised = False
            try:
                AutoRouter().run(private_task, project_root=project)
            except RuntimeError:
                raised = True
            rows = load_outcomes(project)
            _ok("cloud errors preserve caller semantics and still emit FAIL",
                raised and len(rows) == 1 and rows[0]["route"] == "cloud"
                and rows[0]["status"] == "FAIL" and rows[0]["verified"] is False,
                state)
    finally:
        AutoRouter.decide = original_decide
        router_mod.LocalLLMClient = original_client
        router_mod._cloud_chat = original_cloud
        cache_mod._cache.get = original_cache_get
        cache_mod._cache.set = original_cache_set

    print(f"\nRESULT: {state[0]} passed, {state[1]} failed")
    return 0 if state[1] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
