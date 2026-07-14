"""Integration test for the exact response cache in AutoRouter."""

from skills.auto_router.router import AutoRouter
from skills.response_cache import ResponseCache
from skills.tiered_router import Tier


def test_second_identical_local_call_uses_cache(monkeypatch, tmp_path):
    backend = type("Backend", (), {
        "label": "local", "host": "127.0.0.1", "port": 1234,
        "base_url": "http://127.0.0.1:1234/v1",
    })()
    calls = []

    def fake_chat(*_args, **_kwargs):
        calls.append(1)
        return type("Result", (), {"text": "cached answer", "total_tokens": 17})()

    monkeypatch.setattr("skills.auto_router.router.registry.best_chat_backend", lambda: backend)
    monkeypatch.setattr("skills.auto_router.router.registry.preferred_model", lambda _b: "model")
    monkeypatch.setattr("skills.auto_router.router.LocalLLMClient.chat", fake_chat)
    monkeypatch.setattr("skills.response_cache._cache", ResponseCache(str(tmp_path)))
    router = AutoRouter()

    first = router.run("identical", system="system", force_tier=Tier.LOCAL)
    second = router.run("identical", system="system", force_tier=Tier.LOCAL)
    different_limit = router.run(
        "identical", system="system", max_tokens=32, force_tier=Tier.LOCAL,
    )

    assert first["text"] == second["text"] == "cached answer"
    assert second["cached"] is True
    assert second["tokens"] == 0
    assert different_limit.get("cached") is not True
    assert len(calls) == 2
