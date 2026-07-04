"""Tests for nn_router skill."""
from skills.nn_router.router import (
    estimate_complexity, route, batch_route, routing_stats, MODEL_TIERS,
)


def test_nano_route():
    tier, model, score = route("parse JSON config")
    assert tier == "nano"
    assert score <= 2


def test_micro_route():
    tier, model, score = route("validate email address")
    assert tier in ("nano", "micro")
    assert score <= 4


def test_medium_route():
    tier, model, score = route("classify transaction patterns for fraud detection")
    assert tier == "medium"
    assert score >= 4


def test_macro_route():
    tier, model, score = route("design auth middleware with rate limiting")
    assert tier == "macro"
    assert score >= 7


def test_estimate_complexity():
    assert estimate_complexity("parse json") == 1
    assert estimate_complexity("design a custom auth middleware") >= 7


def test_model_tiers():
    assert "nano" in MODEL_TIERS
    assert "micro" in MODEL_TIERS
    assert "medium" in MODEL_TIERS
    assert "macro" in MODEL_TIERS


def test_batch_route():
    tasks = [
        "parse JSON config",
        "validate email",
        "audit code quality",
        "design auth middleware",
    ]
    results = batch_route(tasks)
    assert len(results) == 4
    assert results[0]["tier"] == "nano"
    assert results[3]["tier"] == "macro"


def test_routing_stats():
    tasks = [
        "parse JSON config",
        "strip HTML tags",
        "validate email",
        "audit code quality",
        "design auth middleware",
    ]
    results = batch_route(tasks)
    stats = routing_stats(results)
    assert stats["total_tasks"] == 5
    assert stats["total_cost"] > 0
    assert stats["avg_complexity"] > 0