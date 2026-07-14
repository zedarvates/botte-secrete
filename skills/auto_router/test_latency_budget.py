"""Regression tests for latency and token-budget routing constraints."""

from skills.auto_router.router import AutoRouter
from skills.tiered_router import Tier


def test_sub_two_second_budget_disables_local(monkeypatch):
    backend = type("Backend", (), {
        "label": "local", "host": "127.0.0.1", "port": 1234,
        "base_url": "http://127.0.0.1:1234/v1",
    })()
    monkeypatch.setattr("skills.auto_router.router.registry.best_chat_backend", lambda: backend)
    monkeypatch.setattr("skills.auto_router.router.registry.preferred_model", lambda _b: "model")
    monkeypatch.setattr("skills.auto_router.router.providers.cheapest_cloud_at_least", lambda _t: None)

    decision = AutoRouter(latency_budget_s=1.0).decide(
        "classify this", force_tier=Tier.LOCAL,
    )

    assert decision.mode == "none"
