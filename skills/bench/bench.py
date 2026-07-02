"""botte bench — the reproducible proof behind "N% token savings".

Runs the fixed corpus (`tasks.py`) through the real belt (`auto_router.decide`
— decision only, no network, 0 cloud tokens spent measuring) and compares the
cost of what actually got picked against a fixed baseline: "every task goes
straight to a capable cloud model" (Tier.STANDARD), which is what a project
with no routing does. The delta is the number the README claims — this makes
it checkable instead of asserted.

    python -m skills.bench.cli            # table + totals
    python -m skills.bench.cli --json      # machine-readable
    python -m skills.bench.cli --save md   # timestamped report

Pure stdlib, offline — `decide()` never calls a model, so the whole run costs
0 tokens even though it's simulating what a session with real prompts would do.
"""

from __future__ import annotations

from skills.auto_router.router import AutoRouter
from skills.cost_estimator.cost_estimator import estimate
from skills.tiered_router import Tier
from skills.bench.tasks import BENCH_TASKS

BASELINE_TIER = Tier.STANDARD   # what a project with no routing sends everything to


def run(tasks: list[tuple[str, str]] | None = None) -> dict:
    tasks = tasks if tasks is not None else BENCH_TASKS
    router = AutoRouter()
    rows = []
    with_belt_tokens = with_belt_usd = 0
    baseline_tokens = baseline_usd = 0
    local_count = 0

    for prompt, task_type in tasks:
        decision = router.decide(prompt, task_type=task_type)
        baseline = estimate(task_type, len(prompt), tier=BASELINE_TIER)

        if decision.mode == "local":
            actual_tokens, actual_usd = 0, 0.0
            local_count += 1
        else:
            actual = estimate(task_type, len(prompt),
                              tier=decision.tier if decision.mode == "cloud" else BASELINE_TIER)
            actual_tokens = actual.tokens_in + actual.tokens_out
            actual_usd = actual.usd

        base_tok = baseline.tokens_in + baseline.tokens_out
        rows.append({
            "task": prompt[:60], "task_type": task_type,
            "decision": decision.mode, "tier": decision.tier.name,
            "actual_tokens": actual_tokens, "actual_usd": round(actual_usd, 6),
            "baseline_tokens": base_tok, "baseline_usd": round(baseline.usd, 6),
        })
        with_belt_tokens += actual_tokens
        with_belt_usd += actual_usd
        baseline_tokens += base_tok
        baseline_usd += baseline.usd

    tok_savings_pct = (round((1 - with_belt_tokens / baseline_tokens) * 100, 1)
                       if baseline_tokens else 0.0)
    usd_savings_pct = (round((1 - with_belt_usd / baseline_usd) * 100, 1)
                       if baseline_usd else 0.0)

    return {
        "corpus_size": len(tasks),
        "local_pct": round(local_count * 100 / len(tasks)) if tasks else 0,
        "rows": rows,
        "totals": {
            "with_belt_tokens": with_belt_tokens, "with_belt_usd": round(with_belt_usd, 4),
            "baseline_tokens": baseline_tokens, "baseline_usd": round(baseline_usd, 4),
            "token_savings_pct": tok_savings_pct, "usd_savings_pct": usd_savings_pct,
        },
        "baseline": f"every task sent to {BASELINE_TIER.name} (no routing)",
    }
