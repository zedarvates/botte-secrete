# Parcimonia advisory assessment evaluation

The versioned corpus in `skills/preflight/evaluation_cases.json` checks
`assess_task` directly. It contains 29 authored French and English requests
covering statistics, exact file duplicates, local Markdown links, negation,
quoted instructions, mixed requests and unavailable tools. No model, MCP
execution, network access or provider key is needed by this runner.

```sh
python -m skills.preflight.evaluation --output .botte-cache/assessment-report.json
```

Exit codes are 0 for passing expectations, 1 for failed expectations and 2 for
invalid input or an execution error. The bounded JSON loader rejects duplicate
keys, duplicate case IDs, unknown expectation fields and contradictory criteria.
The canonical Parcimonia test suite includes adversarial evaluator checks.

Each report retains the task, offered metadata, human expectation, complete
assessment and failed criteria. Provenance includes SHA-256 of the assessment,
ranking and evaluator source files, and of sorted compact UTF-8 corpus JSON.
The corpus baseline reference is historical context, not a claim that current
code still equals that commit. Group and split counts preserve failures.

## What a passing case means

| Check | Meaning |
| --- | --- |
| Expected intent and status | The lexical assessor proposes or abstains as authored. |
| Expected candidate present | The supplied tool appears somewhere in the discovery shortlist; its ranking and capability are not established. |
| Forbidden intent or candidate absent | This authored request avoids that inappropriate proposal. |
| Empty, omitted, unrelated inventory or zero budget | Missing metadata is retained rather than fabricated. |
| Advisory boundaries | No execution, network, model use, authorization or measured savings are asserted. |

All tool inventories are fixtures. They do not establish that a particular
Codex host exposes those tools. Local elapsed times cover each assessment call
only; they exclude installation, host startup, tool execution and model work.
Provider usage, billed cost and savings remain unknown.

## Preserved failure and correction

At baseline `229d302641fae4bf068bdb289c0c61a866adb86a`, the same 29 cases
passed 27 expectations. The French request “Donne le 90e percentile des valeurs…”
and English “Give the 90th percentile of…” abstained. The correction accepts a
direct give/report request followed by an optional article and ordinal, then
percentile/quantile and `des`, `de` or `of`. Definitions, explanations, negations,
quoted instructions and mixed code changes retain separate negative witnesses.

The preparation record is
[`validation/parcimonia-assessment-2026-10-31.json`](validation/parcimonia-assessment-2026-10-31.json).
The candidate installation workflow runs the corpus from each independently
installed wheel and uploads `assessment-report.json` beside the installation,
MCP and wheel artifacts. Read the exact-head job conclusion and report together.
The installation verifier compares evaluator and corpus bytes between the
source checkout, wheel and installed package, alongside the exercised runtime.

## Next model evaluation

Each case also stores `codex.action` and `codex.checks` as future review criteria.
The offline runner retains these fields but never grades them: every report
sets `model_selection.status` to `not_run` and evaluated model cases to zero.
Some future cases still need numeric or directory/snapshot fixtures before a
model run. This is a preparation corpus, not a complete live evaluation harness.

For a real Codex evaluation, send only the task and the genuinely available
tool metadata. Keep expectations, case IDs, reports and evaluator files outside
the model's readable workspace. Retain complete genuine traces tied to the model,
reasoning settings, Codex version, plugin/runtime source, tool inventory and
input fixtures. Check tool choice, arguments, result and final answer separately.
Treat absent or truncated traces as indeterminate. A fabricated trace tests a
grader, not a model. These public cases are regression cases; the exploratory
`challenge` label does not identify a held-out sample or prove generalization.

The distinction between direct tools and product-harness evaluation follows
the [OpenAI plugin evaluation example](https://developers.openai.com/cookbook/examples/partners/harness_aware_plugin_evals/harness_aware_plugin_evals).
