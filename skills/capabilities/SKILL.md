---
name: capabilities
layer: GOVERN
description: The system's self-model — a capability registry (scans every SKILL.md into a layered tree SENSE→DECIDE→ACT→REMEMBER→GOVERN→DEPLOY) plus a "curator" that picks the right capabilities for a goal locally. Use to see the whole toolkit as a system/arborescence, to let an agent discover what botte-secrète can do, or as the data the Conductor reads to compose a plan.
---

# capabilities — the system's map of itself (registry + curator)

Turns the discovered modules from a *collection* into a *system*: one self-describing
tree the rest can reason over.

```bash
python -m skills.capabilities.cli map               # ASCII layered system tree
python -m skills.capabilities.cli list --json       # the registry
python -m skills.capabilities.cli curate "test my desktop app"
python -m skills.capabilities.cli list --json --effects  # opt-in declarations
python -m skills.capabilities.cli effects skills/capabilities
```

## Layers (the arborescence)

| Layer | Role |
|-------|------|
| **SENSE** | understand project / cluster / task |
| **DECIDE** | route the work, cheapest capable |
| **ACT** | do the work, local-first |
| **REMEMBER** | capitalise (compounding) |
| **GOVERN** | consistency & cost control |
| **DEPLOY** | wire into projects & measure |

Each skill's layer comes from a `layer:` field in its SKILL.md frontmatter, else
a built-in map, else ACT. Generated snapshot: [`docs/system-map.txt`](../../docs/system-map.txt).

## The curator

`curate(goal)` ranks the capabilities most relevant to a goal (local lexical
match, **0 tokens**) — the librarian that hands the Conductor (and you) the right
branches of the tree to use. Built on [[skill_finder]].

This registry is the foundation for the Conductor (goal → decision tree → ordered
plan of capabilities, executed local-first) and the control loop (measure → adapt).
Related: [[skill_finder]], [[auto_router]], [[bootstrap]].

## Effects, analysis and reuse

When assessing a selected capability's consequences, read its optional
`effects.json` through `effects <skill_dir>` or `load(include_effects=True)`.
Distinguish `missing`, `invalid`, `stale` and `declared`; the last only confirms
structure and listed source hashes, including for drafts. It does not verify
behavior or grant authority. Ordinary registry output remains unchanged.

Relate expected effects to the current task and its existing authorization.
After use, record observed effects, evidence, deviations, uncertainties and the
next action through the task's existing report. For plausible reuse, state what
transfers, adaptations and a check in the target context; do not inherit a prior
validation or permission automatically.

When creating or updating declarations, use the read-only `template` command and
the [authoring contract](../../docs/capability-effects.md). Keep substantial
details in the sidecar, loaded only when needed. The registry's own declaration
covers discovery and inspection, not execution of the capabilities it lists.
