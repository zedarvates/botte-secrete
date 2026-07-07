"""Effort classifier — regression test fixtures.

Versioned corpus of prompts with expected effort tiers, used to detect
regression after threshold/model changes.
"""

REGRESSION_CORPUS = [
    # (prompt, expected_tier, description)
    ("fix typo", "FREE", "trivial"),
    ("rename variable in 3 files", "LOCAL", "simple code"),
    ("add type hints to module", "LOCAL", "code improvement"),
    ("refactor authentication middleware", "STANDARD", "complex refactor"),
    ("audit security across entire codebase", "PREMIUM", "security audit"),
    ("design distributed cache architecture", "PREMIUM", "architecture design"),
    ("sort imports", "FREE", "mechanical"),
    ("debug race condition in async code", "STANDARD", "debugging"),
    ("format code with auto-formatter", "LOCAL", "formatting"),
    ("write integration tests for payment flow", "STANDARD", "test writing"),
    ("explain the CAP theorem", "CHEAP", "explanation"),
    ("migrate database schema with zero downtime", "PREMIUM", "migration"),
    ("optimize N+1 query problem", "STANDARD", "optimization"),
    ("add docstring to function", "LOCAL", "documentation"),
    ("fix memory leak in C extension", "PREMIUM", "low-level fix"),
]


def run_regression_test() -> dict:
    """Run all regression prompts through effort estimator, report mismatches."""
    from skills.auto_router.effort import estimate

    passed = 0
    failed = []
    for prompt, expected, desc in REGRESSION_CORPUS:
        result = estimate(prompt)
        if result.tier.name == expected:
            passed += 1
        else:
            failed.append({
                "prompt": prompt,
                "expected": expected,
                "got": result.tier.name,
                "score": round(result.score, 3),
            })

    return {
        "total": len(REGRESSION_CORPUS),
        "passed": passed,
        "failed": len(failed),
        "rate": round(100 * passed / len(REGRESSION_CORPUS), 1),
        "failures": failed,
    }
