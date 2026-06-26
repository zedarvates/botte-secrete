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

        nn_belt.local_vs_cloud_hint = lambda *a, **k: None  # abstain
        d2 = AutoRouter().decide("borderline task")
        _ok("abstaining belt does not claim the decision",
            "NN belt" not in d2.reason, state)
    finally:
        registry.best_chat_backend = o_best
        registry.preferred_model = o_pref
        nn_belt.local_vs_cloud_hint = o_hint
        router_mod.estimate_effort = o_est

    # 12. Implicit feedback: belt decisions get labelled for the active-learning loop.
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
        rows = [_json.loads(x) for x in logf.read_text().splitlines() if x.strip()]
        _ok("record_feedback appends one labelled row (correct=False)",
            len(rows) == 1 and rows[0]["actual_class"] == 1 and rows[0]["correct"] is False,
            state)

        d_no = AutoDecision(mode="cloud", tier=Tier.CHEAP, effort=effort.estimate("x"))
        _ok("record_override no-ops without belt context",
            AutoRouter().record_override(d_no, "cloud") is False, state)

        d_belt = AutoDecision(mode="local", tier=Tier.LOCAL, effort=effort.estimate("x"),
                              _belt_ctx={"features": [0.5, 1.0, 1.0], "predicted_class": 0})
        logged = AutoRouter().record_override(d_belt, "cloud")
        rows2 = [_json.loads(x) for x in logf.read_text().splitlines() if x.strip()]
        _ok("record_override logs a correction (local→cloud) when belt drove it",
            logged and len(rows2) == 2 and rows2[1]["actual_class"] == 1, state)
    finally:
        al_mod.DATA_DIR = o_data

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
