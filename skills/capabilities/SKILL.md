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

Use `load(..., preserve_paths=True)` to retain every `SKILL.md` path even when
folders or names repeat. Use `curate(..., include_paths=True)` to associate candidates
with metadata; display names alone are not identities. This opt-in adds `path`
without reading effects declarations or changing the default curation fields.

This registry is the foundation for the Conductor (goal → decision tree → ordered
plan of capabilities, executed local-first) and the control loop (measure → adapt).
Related: [[skill_finder]], [[auto_router]], [[bootstrap]].

## Effects, analysis and reuse

When assessing a selected capability's consequences, read its optional
`effects.json` through `effects <skill_dir>` or `load(include_effects=True)`.
The inspector checks the identity resolved from the bundled path. For external
trees, pass the trusted expected `--id` / `expected_id` or a registry
`capability_namespace`; do not reuse the sidecar's claim as its own identity
proof. Effects-aware discovery retains colliding folder paths for inspection.
Distinguish `missing`, `invalid`, `stale` and `declared`; the last only confirms
structure, resolved identity and listed source hashes, including for drafts. It does not verify
behavior or grant authority. Ordinary registry output remains unchanged.

Use the shared [effect-review method](../effect-review/SKILL.md) for before/after
assessment and a concrete reuse proposal. `skills.capabilities.review` generates
compact deterministic cues for Conductor `--review-effects`, without an LLM call.
Detailed operation prose stays in sidecars; the compact view defers its assessment.
Use `effects <skill_dir> --select /retry` or Python `review.read_details` to fetch
selected sections. Pass `--expect-sha256` / `expected_sha256` from the review to
detect changed declarations. See the [detail-reading guide](../../docs/capability-effects.md#read-deferred-details).

When creating or updating declarations, use the read-only `template` command and
the [authoring contract](../../docs/capability-effects.md). Keep substantial
details in the sidecar, loaded only when needed. The registry's own declaration
covers discovery and inspection, not execution of the capabilities it lists.

For runtime comparison, the [observation companion](../../docs/capability-effects.md#observe-and-reconcile-a-run)
provides `ObservationSession`, `validate_report` and `summarize` in
`skills.capabilities.observations`. Opt-in v2 collection records instrumented call
links, bounded file evidence and TCP/HTTP response metadata; v1 reports remain
readable. Network targets have opaque run-local aliases, with no payloads or
credentials. A checkpoint writes a caller-selected report file. Propagate worker
contexts explicitly with `submit_observed` and join them before session closure;
late completions cannot rewrite a closed report. There is no automatic tracing
or execution of verification text. Keep whole effects and reuse unverified when
only a write or transport-response facet was sampled.

Start a saved execution handoff with `evidence <report.json> --overview` for all
steps and evidence references. Use `--result 0` for one saved Conductor step,
or omit both options for a standalone companion. An index precedes
optional `--select /observations/o1` reads; carry `--expect-sha256` from that index
or `review_after`. Python equivalents are in `skills.capabilities.evidence`.
See the [evidence-reading guide](../../docs/capability-effects.md#read-retained-evidence).
