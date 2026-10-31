---
name: context_budget
description: Propose skills/docs within a token budget using lexical ranking and a conservatively quantized knapsack. Use to shortlist optional context before reading its complete instructions; this does not verify applicability, resolve dependencies or execute skills.
---

# Context budget — shortlist optional context

`select_skills` reads a skill catalog, ranks candidates lexically and returns
references chosen by a deterministic knapsack. It makes no inference request.
Read [effects.json](effects.json) and the
[common effects contract](../../docs/capability-effects.md) for its consequences.

```bash
python -m skills.context_budget.cli "optimize slow postgres queries and add tests" --budget 3000
python -m skills.context_budget.cli "<task>" --budget 4000 --json
```

## Operation boundaries

| Operation | What it does |
|---|---|
| `select_skills(query, budget=4000, roots=None, pool=40)` | Read `SKILL.md` files through `skill_finder`, then rank up to `pool` candidates and choose from that shortlist. Invalid negative/non-integer budget or pool returns an error. |
| `knapsack(items, budget, unit=20)` | Optimize caller-supplied `Item(name, kind, tokens, relevance, ref)` objects for rounded-up token costs. Reject invalid costs, non-finite scores and nonpositive units. |
| CLI and MCP `context_budget` | Return proposals and estimated costs; CLI can print JSON. They do not load the chosen instructions into the agent or execute them. |

The default roots cover this repository's skills. Explicit roots can disclose
other skill names, descriptions and paths through returned references; catalog
loading reads complete files into memory. It deduplicates resolved paths, not
display names. Chosen and dropped entries retain distinct paths for homonyms.
`dropped` covers unselected members of the shortlist, not every catalog omission.

Costs are estimated by `skill_finder` from character counts, not the target
model's tokenizer. Each item is charged `max(1, ceil(tokens / unit))` units;
capacity is `floor(budget / unit)`. The solver is exact for that rounded problem,
which can exclude a feasible original combination: an 11-token item fits an
11-token budget but is omitted with `unit=20`. Even a zero-cost item consumes one
unit. Smaller units improve resolution at higher CPU/memory cost. Two DP tables
scale with candidate count and effective capacity, capped at summed item weights.

`tokens_used`, `relevance_captured`, `catalog_tokens` and `savings_note` describe
this proposal. They are not measured provider tokens, semantic quality or observed
savings. Reading instructions, linked resources and later outputs adds costs.
Lexical matching can miss synonyms or prefer a misleading name; `pool` and the
ranking threshold can exclude useful candidates before optimization begins.

## Choose and reuse in context

Reserve mandatory instructions and required dependencies outside this optional
selection, and deduct their cost from the available budget. The solver has no
mandatory-item, dependency or exclusion-group constraint. Before using a chosen
skill, read its complete instructions and check the operation's suitable cases,
exclusions, prerequisites and effects against the actual task. A score or selected
reference grants no authority to execute or to discard required instructions.

There are no intended persistent writes here. A retry recomputes from the current
catalog, which may have changed. To compare proposals, retain the query, budgets,
unit/pool settings, catalog revisions and returned paths within the authorized
task scope. The module does not capture an immutable source snapshot. Discarding a
proposal cannot undo decisions another agent has already made from it.

Plausible reuse: shortlist optional documents for another workflow by supplying
explicit costs and scores. Validate the target tokenizer, required information,
path identity and representative task results before accepting the selection.
Fixture tests establish bounded selection behavior and quantization limits;
they do not establish production quality or a general savings percentage.
