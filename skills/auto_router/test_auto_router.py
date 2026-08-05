#!/usr/bin/env python3
"""Tests for auto_router — decision logic offline, plus live local if a backend is up.

    python -m skills.auto_router.test_auto_router
"""

from __future__ import annotations

import contextlib
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


@contextlib.contextmanager
def _stub_local_llm(answer: str):
    """Deterministic local LLM (canned reply, backend forced reachable) so the
    live vote path is tested without depending on the loaded model."""
    import skills.llm_backends.client as _c
    o_chat, o_init, o_best = (_c.LocalLLMClient.chat, _c.LocalLLMClient.__init__,
                              registry.best_chat_backend)
    _c.LocalLLMClient.__init__ = lambda self, *a, **k: None
    _c.LocalLLMClient.chat = lambda self, *a, **k: type("_R", (), {"text": answer})()
    registry.best_chat_backend = lambda *a, **k: object()
    try:
        yield
    finally:
        _c.LocalLLMClient.chat, _c.LocalLLMClient.__init__ = o_chat, o_init
        registry.best_chat_backend = o_best


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

    # 8. Vote over a (stubbed, deterministic) local backend returns the answer.
    with _stub_local_llm("Paris"):
        res = fusion.vote("Capital of France, one word only.", max_tokens=24)
        _ok(f"vote returns the local ballot answer ({res.get('total', 0)} ballot(s))",
            res.get("answer") == "Paris", state)

    # 9. NN belt — featurize maps & clamps to binary_router's 3 features.
    from skills.auto_router import nn_belt
    _ok("featurize clamps out-of-range to [0,1]",
        nn_belt.featurize_binary_router(1.5, -0.2, True) == [1.0, 0.0, 1.0], state)
    _ok("featurize encodes has_local as 0/1",
        nn_belt.featurize_binary_router(0.3, 0.9, False) == [0.3, 0.9, 0.0], state)

    # 10. binary_router hint: trivial + local available → 'local' (or abstain),
    # never 'cloud', and never raises.
    hint_easy = nn_belt.local_vs_cloud_hint(0.1, 1.0, has_local=True)
    _ok("hint for easy+local is 'local' or abstain (never cloud)",
        hint_easy is None or hint_easy[0] == "local", state)

    # 11. Router belt-pull: effort forced to a borderline CHEAP tier + a local
    # backend → a confident 'local' hint routes local with 0 cloud tokens, and an
    # abstaining belt leaves the decision alone. Stubbed for determinism (the live
    # tier depends on control-loop-tuned thresholds).
    from skills.auto_router import router as router_mod

    class _FakeBackend:
        label, host, port = "LM Studio", "127.0.0.1", 1234
        base_url = "http://127.0.0.1:1234/v1"

    fake_eff = effort.EffortEstimate(score=0.43, tier=Tier.CHEAP, reasons=[])
    o_best, o_pref, o_hint, o_est = (registry.best_chat_backend,
                                     registry.preferred_model,
                                     nn_belt.local_vs_cloud_hint,
                                     router_mod.estimate_effort)
    registry.best_chat_backend = lambda *a, **k: _FakeBackend()
    registry.preferred_model = lambda *a, **k: "local-model"
    router_mod.estimate_effort = lambda *a, **k: fake_eff
    try:
        nn_belt.local_vs_cloud_hint = lambda *a, **k: ("local", 0.9)
        d = AutoRouter().decide("borderline task")
        _ok("confident 'local' hint → mode=local via NN belt",
            d.mode == "local" and "NN belt" in d.reason, state)

        # Belt 1 abstains → Belt 2.0 (cloud_escalation_predictor) gets a say.
        from skills.auto_router import nn_belt2
        o_hint2 = nn_belt2.cloud_escalation_hint

        nn_belt.local_vs_cloud_hint = lambda *a, **k: None  # belt1 abstains
        nn_belt2.cloud_escalation_hint = lambda *a, **k: ("local_small", 0.8)
        d2b = AutoRouter().decide("borderline task")
        _ok("belt1 abstains → confident belt2 'local_small' routes local",
            d2b.mode == "local" and "NN belt2" in d2b.reason, state)

        nn_belt2.cloud_escalation_hint = lambda *a, **k: ("cloud", 0.9)
        d2c = AutoRouter().decide("borderline task")
        _ok("belt2 'cloud' verdict never claims the decision (advisory only)",
            "NN belt2" not in d2c.reason, state)

        nn_belt2.cloud_escalation_hint = lambda *a, **k: None  # both abstain
        d2 = AutoRouter().decide("borderline task")
        _ok("abstaining belts do not claim the decision",
            "NN belt" not in d2.reason, state)
    finally:
        registry.best_chat_backend = o_best
        registry.preferred_model = o_pref
        nn_belt.local_vs_cloud_hint = o_hint
        nn_belt2.cloud_escalation_hint = o_hint2
        router_mod.estimate_effort = o_est

    # 12. Belt observations remain unlabelled until an explicit verdict arrives.
    import json as _json
    import tempfile
    from pathlib import Path as _Path
    from skills.botte_nn import active_learning as al_mod
    from skills.auto_router.router import AutoDecision

    o_data = al_mod.DATA_DIR
    al_mod.DATA_DIR = _Path(tempfile.mkdtemp()) / "al"
    try:
        al_mod.record_feedback("binary_router", [0.2, 1.0, 1.0],
                               predicted_class=0, actual_class=1)
        logf = al_mod.DATA_DIR / "inference_logs.jsonl"
        rows = [_json.loads(x) for x in logf.read_text(encoding="utf-8").splitlines()
                if x.strip()]
        _ok("record_feedback appends one labelled row (correct=False)",
            len(rows) == 1 and rows[0]["actual_class"] == 1
            and rows[0]["correct"] is False and rows[0]["verified"] is True,
            state)

        observation_id = al_mod.record_observation(
            "binary_router", [0.3, 1.0, 1.0], predicted_class=0,
            outcome="local_returned")
        rows = [_json.loads(x) for x in logf.read_text(encoding="utf-8").splitlines()
                if x.strip()]
        _ok("automatic observation has no invented ground-truth label",
            len(rows) == 2 and rows[1]["actual_class"] is None
            and rows[1]["correct"] is None and rows[1]["verified"] is False
            and rows[1]["outcome"] == "local_returned", state)

        verdict_id = al_mod.record_verdict(observation_id, actual_class=1)
        rows = [_json.loads(x) for x in logf.read_text(encoding="utf-8").splitlines()
                if x.strip()]
        _ok("explicit verdict links a verified label to its observation",
            len(rows) == 3 and verdict_id == rows[2]["inference_id"]
            and rows[2]["source_observation_id"] == observation_id
            and rows[2]["actual_class"] == 1 and rows[2]["verified"] is True,
            state)
        try:
            al_mod.record_verdict(observation_id, actual_class=0)
            duplicate_rejected = False
        except ValueError:
            duplicate_rejected = True
        _ok("an observation cannot be verified twice", duplicate_rejected, state)

        d_no = AutoDecision(mode="cloud", tier=Tier.CHEAP, effort=effort.estimate("x"))
        _ok("record_override no-ops without belt context",
            AutoRouter().record_override(d_no, "cloud") is False, state)

        d_belt = AutoDecision(mode="local", tier=Tier.LOCAL, effort=effort.estimate("x"),
                              _belt_ctx={"features": [0.5, 1.0, 1.0], "predicted_class": 0})
        router_observation_id = AutoRouter._log_observation(d_belt, "local_returned")
        logged = AutoRouter().record_override(d_belt, "cloud")
        rows2 = [_json.loads(x) for x in logf.read_text(encoding="utf-8").splitlines()
                 if x.strip()]
        _ok("router observation returns the feedback id exposed to callers",
            isinstance(router_observation_id, str) and len(router_observation_id) == 32,
            state)
        _ok("record_override logs a correction (local→cloud) when belt drove it",
            logged and len(rows2) == 5 and rows2[4]["actual_class"] == 1
            and rows2[4]["verified"] is True, state)

        from skills import response_cache as cache_mod
        original_decide = AutoRouter.decide
        original_client = router_mod.LocalLLMClient
        original_cache_get = cache_mod._cache.get
        original_cache_set = cache_mod._cache.set

        class _Result:
            text = "verified later"
            total_tokens = 7

        class _Client:
            def chat(self, *_args, **_kwargs):
                return _Result()

        AutoRouter.decide = lambda self, *_args, **_kwargs: d_belt
        router_mod.LocalLLMClient = _Client
        cache_mod._cache.get = lambda *_args, **_kwargs: None
        cache_mod._cache.set = lambda *_args, **_kwargs: None
        try:
            run_result = AutoRouter().run("unique feedback-id contract test")
        finally:
            AutoRouter.decide = original_decide
            router_mod.LocalLLMClient = original_client
            cache_mod._cache.get = original_cache_get
            cache_mod._cache.set = original_cache_set
        _ok("executed belt route includes a verifiable feedback_id",
            run_result.get("text") == "verified later"
            and len(run_result.get("feedback_id", "")) == 32, state)
    finally:
        al_mod.DATA_DIR = o_data

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
