---
name: auto_router
description: Auto-decide whether a task runs on a LOCAL model or a CLOUD model (DeepSeek, GLM, Nemotron, Grok, Gemma, …) from an automatic effort estimate, and run multi-model fusion (cascade, draft→refine, vote). Use when the user wants automatic local-vs-cloud routing, to add cloud LLM providers, to make local and cloud models collaborate, or mentions effort-based routing, model fusion/ensemble, OpenRouter, DeepSeek, GLM, Nemotron, or Grok.
---

# auto_router — effort-based local↔cloud routing + fusion

Estimates a task's tier, then selects an available backend from the configured
registry and catalog. Tier order is a heuristic; it does not prove model quality
or current provider pricing. Extends
`tiered_router` (cost tiers) and `llm_backends` (local discovery) with a cloud
catalog and ensemble strategies.

## When to use

- "Pick local or cloud automatically based on how hard the task is."
- "Use DeepSeek / GLM / Nemotron / Grok / Gemma alongside my local models."
- "Have a local model draft and a stronger model refine" (fusion).
- The user mentions effort routing, model fusion/ensemble, OpenRouter, or any of
  the cloud providers above.

## Auto-decision

Persisted effort thresholds must contain four finite, strictly increasing numeric
values in `[0, 1]`. Invalid configuration falls back to the defaults without
rewriting the file. See [control_loop](../control_loop/SKILL.md) before applying
a shared threshold change; valid values do not establish a good routing policy.

```bash
python -m skills.auto_router.cli route "classify: bug or feature?"   # → LOCAL
python -m skills.auto_router.cli route "design a distributed cache and prove correctness"
python -m skills.auto_router.cli run   "summarize this PR in 2 lines" --max-tokens 200
```

Effort is scored from prompt signals (length, code, stack traces, reasoning vs
trivial vocabulary, multi-file scope) → a `Tier`. `Tier ≤ LOCAL` with a local
backend runs local (0 cloud tokens); higher tiers pick the cheapest available
cloud model, budget-aware, and **fall back to local** when no cloud key is set.
When a non-forced route has both local and cloud as meaningful options, the NN
belt records its raw prediction in shadow mode even if the heuristic remains in
control. Executed local and cloud routes then include a `feedback_id`. Verify it
with `route_feedback` (or
`python -m skills.botte_nn.active_learning verify <id> local|cloud`) only after
the correct route is known; a backend return/failure is telemetry, not a label.

Executed routes also attempt to emit a private `botte.quality-outcome/v1` lifecycle
envelope. A returned or cached answer is unverified `PARTIAL`, an unavailable
route is `ABSTAINED`, and a backend error is unverified `FAIL`. Pass
`--execution-id` to deduplicate that outcome ledger. This does not deduplicate
backend execution or cache writes. The identifier and task text are hashed in
that ledger; the separate response cache can retain plaintext prompts and answers.
These router facts can neither
activate a learned route nor promote themselves to Quality Compass labels.

## Cloud providers

```bash
python -m skills.auto_router.cli providers   # catalog + which are available now
```

Data-driven catalog in `providers.py` — DeepSeek (chat/reasoner), Zhipu GLM,
NVIDIA Nemotron, xAI Grok, Google Gemma. Reach them two ways:

- **OpenRouter** — set `OPENROUTER_API_KEY`, every model by slug, one endpoint.
- **Native** — set the provider's own key (`DEEPSEEK_API_KEY`, `XAI_API_KEY`,
  `ZHIPUAI_API_KEY`, `NVIDIA_API_KEY`), used in preference to OpenRouter.

A model is only routed to when its key is present. Add a row to `CATALOG` and it
routes — slugs/versions are editable defaults.

## Fusion (models collaborating)

```bash
python -m skills.auto_router.cli fusion cascade "is 17 prime?"            # cheap→escalate
python -m skills.auto_router.cli fusion draft   "explain the CAP theorem" # local drafts, cloud refines
python -m skills.auto_router.cli fusion vote    "capital of France, one word?"  # consensus
```

- **cascade** — local/cheap first; escalate to a stronger model only if the
  answer looks low-confidence.
- **draft_refine** — local model drafts (local compute), a cloud model polishes.
  This is the "local + cloud together" mode.
- **vote** — available models answer; select the most common normalized answer.

All fusion modes degrade gracefully with no cloud key (local-only).

The refinement request includes the original question **and the local draft**.
Voting sends the prompt to every available cloud catalog candidate. Fusion's
direct cloud calls bypass `AutoRouter` budget accounting and the response cache;
there is no aggregate spending cap. Cascade's confidence check is a phrase/length
heuristic; voting normalizes and truncates answers. Neither establishes correctness.

## Effects, failure and reuse

Read [effects.json](effects.json) and the
[common contract](../../docs/capability-effects.md) for the selected operation.
Related declarations: [tier estimates](../tiered_router/effects.json),
[backend access](../llm_backends/effects.json),
[events](../events/effects.json) and [outcomes](../trajectory/effects.json).

| Operation | Consequences and limits |
|---|---|
| `route`, `route --explain`, `providers` | Read configuration, registry, environment-key availability and optional learned routing state. No inference request. Explain output includes a prompt excerpt. Catalog availability means a key is present, not that the endpoint is healthy. |
| Python `force_tier=Tier.FREE` | Explicit zero is honored. AutoRouter can still call a local LLM; FREE is a routing tier, not proof of zero computation. With no usable local route it returns `none`. |
| `run` | Consult the cache; on a miss transmit prompt/system text to a local or cloud endpoint. Emit best-effort events, feedback observations, control-loop telemetry and outcome records; update cache entries/statistics. |
| `run` after an unavailable route or local failure | Return JSON with `error`; CLI exits 1. A local failure does not trigger or claim a cloud retry. Cloud exceptions still propagate. Successful text remains unverified. |
| `fusion` | May make several inference calls and expose intermediate answers. Returned agreement, confidence and process success are not independent task evidence. |

Cache reuse binds exact UTF-8 prompt bytes, model, system text, task type, output
limit, mode, selected endpoint/transport and resolved project path. Legacy entries
without this context are misses. This does not isolate storage or credentials:
the shared cache keeps plaintext, has no automatic freshness TTL, and does not
track changes to repository contents, model weights, credentials or external facts.
An unreadable project scope disables cache access for that call. Local execution
selects its backend again, so the decision snapshot is not an endpoint lock.

Budget checks use approximate input/output counts and static tier rates. Accounting
is per router instance, has no automatic calendar reset and cannot cancel already
accepted requests. The latency option suppresses local routing below two seconds;
it is not an end-to-end timeout. No savings percentage or billing limit follows
from a tier choice, cache hit counter or returned token count alone.

Before a retry, check whether inference completed and whether an answer, cache
entry or outcome already exists. A timeout can leave remote work running; a retry
may spend again. Restore local files only from an appropriate prior snapshot and
account for concurrent writers. Sent data, remote logs and consumed compute cannot
be recalled here. Existing task scope must cover the actual recipients and inputs;
an available API key, declaration or model response grants no new authority.

For another workflow, validate representative prompts, changed context, backend
failures, actual usage and independent task quality before accepting cached results
or learned routing corrections. The isolated routing fixtures establish specific
call/cache behavior, not provider quality or production savings. These entry points
have no complete effect-observation adapter; dependency observations remain partial.

## MCP

Exposed via [[llm_mcp]] as tools `auto_route`, `route_feedback`, and `fusion`, so
an agent can route, verify, and fuse on its own. Related: `tiered_router`,
`llm_backends`, `response_cache`.
