# Memory quarantine contract — 2026-08-27

Status: Draft implementation contract for issue #86.

## Goal

Prevent externally sourced text from silently becoming trusted executable guidance when persisted by `auto_memory`.

## Trust model

Every memory entry records:

- `source_type`: `user`, `repo`, `web`, `tool`, `agent`, or `generated`;
- `source_id`: optional source URI/identifier;
- `run_id`: optional Gauntlet run identifier;
- `trust_class`: `trusted`, `project`, `external`, `generated`, or `quarantined`;
- `executable_instruction`: false by default;
- `quarantined`: true by default for web/repo/tool/agent/generated input unless explicitly classified otherwise.

The legacy `store(key, value, category, confidence, tags)` API remains valid and keeps a conservative default provenance of `generated/quarantined` unless the caller supplies trusted provenance.

## Retrieval rules

Normal `recall()` and `search()` must not surface quarantined memories unless the caller explicitly opts in. Quarantined entries remain inspectable through dedicated metadata-aware methods so they can be reviewed, scored, sanitized, promoted, or forgotten.

Retrieval does not turn stored text into instructions. `executable_instruction` is metadata only and defaults to false. Any future executor must enforce its own policy before using recalled content as an action directive.

## Promotion

Promotion from quarantine is explicit and auditable. A promoted entry retains provenance and receives a new `updated_at` timestamp. Promotion must never mutate `source_type`, `source_id`, or `run_id` to hide origin.

## Compatibility

Older `index.json` rows lacking provenance fields load with safe defaults. This avoids breaking existing stores while preventing old entries from acquiring implicit execution authority.

## Validation fixtures

Tests must cover:

1. old-format row loads successfully;
2. external memory is quarantined by default;
3. normal recall does not return quarantined data;
4. explicit include-quarantined inspection can retrieve it;
5. trusted user/project memory remains normally recallable;
6. promotion changes quarantine state but preserves provenance;
7. executable instructions remain false unless explicitly supplied by a trusted caller.
