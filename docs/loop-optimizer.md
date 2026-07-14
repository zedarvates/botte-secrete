# Loop Optimizer

The Loop Optimizer reduces the cost of retroactive agent loops without handing
safety decisions to a model. It decides only; it never executes a tool,
command, network request, or cloud escalation.

## Safe startup

The controller runs in `shadow` mode by default. It records a local proposal
without changing the existing execution pipeline.

```bash
python -m skills.loop_optimizer.cli explain demo-loop "verify targeted tests" --tools run_tests
python -m skills.dashboard.cli . --tui
```

| Variable | Values | Default |
|---|---|---|
| `BOTTE_LOOP_OPTIMIZER` | `0`, `shadow`, `1` | `shadow` |
| `BOTTE_NEEDLE_ROUTER` | `0`, `shadow`, `1` | `0` |

`0` disables a feature, `shadow` observes only, and `1` is reserved for an
explicitly approved rollout.

## Decision order

1. budgets, progress, and repeated failures;
2. exact cache;
3. lexical tool filter;
4. Belt 2.0 advisory predictors;
5. local LLM;
6. cloud, only when the existing router permits it.

The final verification remains global even when intermediate iterations check
only changed deltas.

## MCP commands

- `loop_decide`: deterministic proposal;
- `loop_explain`: decision, skipped layers, and state;
- `loop_record`: record an already verified result;
- `loop_stats`: aggregate local metrics.

These commands never execute proposed tools.

## Needle: optional experiment

Needle is never required. The adapter abstains when its runtime or weights are
missing, receives at most ten tools and 1,024 estimated input tokens, and
validates arguments before returning an executable route.

It may be enabled only when a local benchmark simultaneously demonstrates:

- tool accuracy of at least 95%;
- valid argument accuracy of at least 98%;
- zero dangerous false routes;
- p95 latency below the compared local LLM.

The seed corpus is in
[`skills/tool_router/eval_dataset.jsonl`](../skills/tool_router/eval_dataset.jsonl).
It validates wiring and safety; it is not a training dataset.

## Progressive rollout

Policy learning and live activation remain blocked until 2,000 verified Botte
trajectories are collected. Then each 10%, 50%, and 100% stage requires at
least 100 scenarios with no regression. No CogniARC code, dataset, or protocol
is involved.
