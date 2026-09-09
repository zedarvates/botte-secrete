---
name: tiered_router
description: Estimate model tiers and token costs, track caller-recorded usage, or inspect in-memory response caching and agent delta helpers. Use when integrating budget-aware routing or analyzing its limits; this module does not execute model calls.
---

# Tiered router

Use `TieredRouter` to propose a tier and record explicit usage. Consult
[effects.json](effects.json) and the [effects contract](../../docs/capability-effects.md)
before reusing its estimates or shared state. For endpoint selection and execution,
see [auto_router](../auto_router/SKILL.md).

```python
from skills.tiered_router import Budget, Tier, TieredRouter

router = TieredRouter(Budget(daily=50000, per_call=8000, monthly_cost=5.0))
proposal = router.route("code_review", "review this fixture")
free = router.route("static_analysis", "fixture", force_tier=Tier.FREE)
```

| Operation | Effect and interpretation |
|---|---|
| `route`, `estimate_tokens`, `estimate_cost` | Return an estimate using task mappings, text length and static tier rates. No model or network call; no budget reservation. Explicit `Tier.FREE` is honored. |
| `Budget.spend`, `record` | Increment instance counters; `record` also appends history. Repeating the same call records it again. Supply nonnegative real token counts and record each actual execution once. |
| `cache_response` | Store a caller-keyed response in memory; beyond 500 entries evict the oldest insertion timestamp. `route` recognizes a matching task/text key for 24 hours. |
| `report` | Aggregate caller-supplied history. The premium comparison uses a rough fixed per-call baseline, not equivalent measured provider requests. |
| `AgentCompressor` | Keep a shared knowledge map and transmission-size history in memory; omit known fields or list members and merge partial dictionaries. No messages are sent. |

Tier labels are FREE, LOCAL, CHEAP, STANDARD and PREMIUM. Their token quantities
are nominal examples, not enforced limits or hardware measurements. Prices are
static estimates. `local_available` only indicates a locally eligible tier; no
backend has been probed. A budget-exhausted proposal can still return a LOCAL
fallback without a usable backend or sufficient token budget. Validate feasibility
and actual recipients in the executing caller.

Budgets and caches belong to Python objects, not automatically to projects or
calendar periods. There is no persistence, date rollover, cross-process lock or
reservation for concurrent callers. `record` does not enforce the cap. New
instances reset these counters unless the caller explicitly restores them.

The tiered cache key covers task type and input text only. It does not bind model,
system prompt, project, requested tier or current source state. A hit is an advisory
FREE proposal; it does not authenticate the cached response. Scope each instance
and invalidate entries when omitted context changes. Responses and shared values
are held by reference, so later caller mutation can change retained state.

`AgentCompressor` is a partial merge helper, not a lossless state synchronization
protocol: known list members can be omitted while `decompress` replaces the list;
deletions, reordering and nested shared-key collisions can lose or retain wrong
state. Receiver knowledge is assumed unless supplied. Keep full source data and
validate reconstruction before using the result. Character-size counters are not
measured token savings and nested calls also add history entries.

For retries, distinguish reading an estimate from recording usage or inserting
cache data. Repeating a write can double-count cost or change eviction order.
Recover from a prior caller-owned snapshot if available and reconcile downstream
actions separately. Dropping the object does not undo work another caller already
performed from its proposal.

Plausible reuse: compare tier proposals in an offline routing experiment using
isolated instances, explicit budgets and representative tasks. Validate actual
availability, measured usage and task correctness in the target context before
adopting a routing policy. No guaranteed savings percentage is established here.
