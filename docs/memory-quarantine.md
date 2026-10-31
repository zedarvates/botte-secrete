# Memory quarantine and provenance

Memory Hub treats remembered content as data, never as policy. Every MCP proposal
must identify its source, run, observation time, confidence and trust class, and
must set `executable_instruction` to `false`.

## Storage boundary

| Source | Storage | Normal context | Promotion |
|---|---|---|---|
| `user` + `trusted_user` | `memory_entries` | Only after lifecycle review | Allowed by the existing lifecycle |
| `repo`, `web`, `tool`, `agent` | `memory_quarantine` | Excluded | Blocked |
| `generated` | `memory_quarantine` | Excluded | Blocked |
| Legacy entry without provenance | Migrated to `memory_quarantine` | Excluded | Blocked |

Quarantined entries are available only through the explicit
`review_quarantine` tool. Its response marks content
`UNTRUSTED_DATA_DO_NOT_EXECUTE`, carries provenance, and has `SIMULATE`
authority. The normal `context_bundle` reads only reviewed trusted storage and
still attaches provenance to every returned entry.

No Memory Hub call can set `executable_instruction=true`. Text retrieved from a
repository, page, tool or agent therefore cannot silently extend tool policy,
alter authority, or become a durable skill. A future dequarantine workflow must
define independent repeated validations and sanitization; until then the safe
operation is review or deletion.

## Required proposal metadata

- `source_type`: `user`, `repo`, `web`, `tool`, `agent`, or `generated`
- `source_uri` or `source_id` when one exists
- `run_id`
- `timestamp`
- `confidence` between 0 and 1
- `trust_class`: `trusted_user`, `external_observation`, or `generated_untrusted`
- `executable_instruction=false`

The Gauntlet fixture in `skills/memory_hub/test_quarantine.py` stores an
observation that asks to replace the tool allowlist. It verifies physical
quarantine, exclusion from normal context, explicit review labeling, blocked
promotion, non-executable provenance, and fail-closed migration of v1 records.
The machine-readable metadata contract is
[`docs/schemas/memory-provenance.schema.json`](schemas/memory-provenance.schema.json).
