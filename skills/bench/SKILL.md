---
name: bench
layer: GOVERN
description: Reproducible token/cost benchmark — runs a fixed task corpus through the real auto_router decision logic and compares it against a "no routing, everything to cloud STANDARD" baseline. Turns the README's savings claim into a checkable number instead of an assertion. Use when the user wants proof of token savings, a benchmark for a PR/README, or numbers to back an integration pitch (e.g. Hermes).
---

# bench — the proof behind the savings claim

```bash
python -m skills.bench.cli            # table + totals
python -m skills.bench.cli --json
python -m skills.bench.cli --save md  # timestamped report under .botte/reports/
```

Runs `tasks.py`'s fixed corpus (17 prompts spanning trivial → hard reasoning)
through the real `auto_router.decide()` — **decision only, 0 tokens spent
measuring** — and compares the actual cost of what got picked against a
documented baseline (every task sent straight to Tier.STANDARD, i.e. what a
project with no routing at all pays). The delta is the number: token % saved,
USD % saved, % that stayed local.

## Why this exists

The README says "~65% (reported by users)" — a claim, not a proof. `bench` is
versioned in the repo, runs offline, and gives the same shape of number every
time: `python -m skills.bench.cli` in CI or before a release, diff the
totals against the last run. It's also the evidence for [[preflight]]'s
"prefer local" default and for pitching the belt to other agent frameworks
(see the Hermes-Agent integration proposal in `docs/plans/`).

## Reading the result

- **`local_pct`** — % of the corpus that resolved to a local backend (0 cloud
  tokens for those).
- **`totals.token_savings_pct` / `usd_savings_pct`** — belt cost vs. the fixed
  baseline.
- **Caveat, stated plainly**: the corpus prompts are short (they're meant to
  be reproducible and fast, not exhaustive), so the effort estimator's
  length-based signal under-weights them relative to real production
  prompts — which carry full stack traces, diffs, multi-file context. On a
  machine with a local backend running, this bench tends to read *higher*
  local% than a real session would. Treat it as a floor/sanity-check number,
  not a substitute for `control_loop.analyze()`'s real historical stats.

Related: [[auto_router]] (what's being measured), [[control_loop]] (the real,
historical counterpart), [[cost_estimator]] (the cost model reused here).
