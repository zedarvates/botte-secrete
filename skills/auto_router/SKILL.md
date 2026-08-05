---
name: auto_router
description: Auto-decide whether a task runs on a LOCAL model or a CLOUD model (DeepSeek, GLM, Nemotron, Grok, Gemma, …) from an automatic effort estimate, and run multi-model fusion (cascade, draft→refine, vote). Use when the user wants automatic local-vs-cloud routing, to add cloud LLM providers, to make local and cloud models collaborate, or mentions effort-based routing, model fusion/ensemble, OpenRouter, DeepSeek, GLM, Nemotron, or Grok.
---

# auto_router — effort-based local↔cloud routing + fusion

Decides *for you* how much model muscle a task needs, then sends it to the
cheapest capable backend — local first, cloud when it's worth it. Extends
`tiered_router` (cost tiers) and `llm_backends` (local discovery) with a cloud
catalog and ensemble strategies.

## When to use

- "Pick local or cloud automatically based on how hard the task is."
- "Use DeepSeek / GLM / Nemotron / Grok / Gemma alongside my local models."
- "Have a local model draft and a stronger model refine" (fusion).
- The user mentions effort routing, model fusion/ensemble, OpenRouter, or any of
  the cloud providers above.

## Auto-decision

```bash
python -m skills.auto_router.cli route "classify: bug or feature?"   # → LOCAL
python -m skills.auto_router.cli route "design a distributed cache and prove correctness"
python -m skills.auto_router.cli run   "summarize this PR in 2 lines" --max-tokens 200
```

Effort is scored from prompt signals (length, code, stack traces, reasoning vs
trivial vocabulary, multi-file scope) → a `Tier`. `Tier ≤ LOCAL` with a local
backend runs local (0 cloud tokens); higher tiers pick the cheapest available
cloud model, budget-aware, and **fall back to local** when no cloud key is set.
When the NN belt drives an executed local route, the result includes a
`feedback_id`. Verify it with `route_feedback` (or
`python -m skills.botte_nn.active_learning verify <id> local|cloud`) only after
the correct route is known; a backend return/failure is telemetry, not a label.

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
- **draft_refine** — local model drafts (free), a stronger cloud model polishes.
  This is the "local + cloud together" mode.
- **vote** — several models answer; return the consensus (great for classification).

All fusion modes degrade gracefully with no cloud key (local-only).

## MCP

Exposed via [[llm_mcp]] as tools `auto_route`, `route_feedback`, and `fusion`, so
an agent can route, verify, and fuse on its own. Related: `tiered_router`,
`llm_backends`, `response_cache`.
