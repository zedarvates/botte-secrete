# Action-consequence memory

This opt-in adapter connects the verified Conductor plans to the authenticated
shared Memory Hub. It combines the branches behind PRs #110 and #111. The
existing SQLite service owns access rights, quarantine, receipts and deletion;
the adapter does not create another memory database or a new network boundary.
See the [local acceptance record](validation/action-consequence-memory-v1.json)
for the tested scope and remaining deployment limits.
The [two-identity host pilot](action-memory-homelab-pilot.md) provides a
reproducible producer/consumer check for the configured homelab service.

## What an episode means

An episode is a reported execution observation, encoded as
`botte.action-consequence/v1` inside the existing shared-memory observation
record. See the [episode schema](schemas/action-consequence.schema.json).
It retains the run and step identity, command/contract/context fingerprints,
expected file-check kinds and paths, dependencies, actual file-change samples,
check results and references to the full report and quality outcome envelope.

The shared copy contains no raw goal, command arguments, check values, file
contents or subprocess output. Paths, capability names and hashes may still
be private. Full reports remain in the executing project's private
`.botte/action-evidence/<report-digest>.json` archive; the digest covers canonical
JSON. Capturing a later resume report creates another snapshot and preserves
the original observations. Inspect the full report for declaration text and
the complete dependency evidence.

| Component | Responsibility |
|---|---|
| Conductor report | Local pre/postconditions, dependency gates and checkpointed execution |
| Shared Memory Hub | Scoped, sourced observations and idempotent receipts |
| `trajectory` envelope | Link the same execution to private lifecycle evidence, without a verified task label |
| Action-memory recall | Compare past episodes with the caller's current plan and recheck its declared files |

`reported_status=verified` retains Conductor's meaning: declared local checks
passed. Capture emits a `PARTIAL` quality envelope with no independent verifier
and no task verdict. It does not add support to the verified k-NN ledger. Child
model costs, task quality and complete downstream effects remain unmeasured.
`causal_attribution=not_assessed` separates a before/after observation from a
claim that the action caused it.

## Configure and use

Follow the [shared-service operator guide](shared-memory.md) to configure the
service and a worker identity with the intended project and read/write rights.
Configure the executing CLI or host MCP process, keeping token contents out of
tool arguments:

```bash
export BOTTE_MEMORY_URL=http://127.0.0.1:8766
export BOTTE_MEMORY_TOKEN_FILE=/absolute/private/memory-pilot/worker.secret
```

Use HTTPS or a loopback tunnel from another machine. The existing authenticated
client verifies HTTPS and refuses redirects. The server derives the actor from
the credential; a caller cannot select an actor or curator role in these tools.

```bash
# Preview: no credential read, API call, archive or checkpoint write.
python -m skills.memory_hub.action_cli run --plan task-plan.json \
  --project . --project-id pilot --checkpoint .botte/skill-runs/task.json

# Existing task authority must cover the commands; --confirm selects gated work.
python -m skills.memory_hub.action_cli run --plan task-plan.json \
  --project . --project-id pilot --checkpoint .botte/skill-runs/task.json \
  --execute --confirm

# Inspect previous experience without executing the plan.
python -m skills.memory_hub.action_cli recall --plan task-plan.json \
  --project . --project-id pilot

# Retry ingestion only, using the immutable report snapshot returned by capture.
python -m skills.memory_hub.action_cli capture --plan task-plan.json \
  --report .botte/action-evidence/REPORT_DIGEST.json --project . --project-id pilot
```

Replace `REPORT_DIGEST` with the returned archive name. The `capture` command
also accepts an existing verified-plan checkpoint, provided it matches the
plan. Use the immutable archive when retrying an uncertain transport result.
`--visibility project` shares observations within the server-authorized project;
the default is private to the authenticated actor.

The host `llm_mcp` server exposes `recall_action_memory`, `remember_skill_run`
and `execute_remembered_plan`. The last tool previews by default. Its result is
a separate `botte.remembered-run/v1` envelope with `execution`, `memory_before`
and `memory_after`; the strict underlying skill-run report is unchanged. The
shared MCP service can inspect these same records through `memory_recall` with
`area=observations`.

Python integrations can call `capture_report`, `recall_for_plan` or
`run_with_memory` from `skills.memory_hub.action_memory`. Supply the configured
`MemoryHTTPClient` or a trusted in-process adapter implementing `call(operation,
args)` with a server-configured principal.

## Recall, limits and retries

Recall matches capability identity and compares command, context, source and
condition fingerprints. A change is reported as `different_action`,
`context_changed` or `contract_changed`. For a previously verified report with
matching bindings, only the current caller-supplied plan chooses file reads.
Remembered paths never choose local read targets. A failed current predicate
is `stale`; missing source bindings remain `unbound_sources`.
`local_checks_match` is a fresh local observation, not permission to repeat a
command or proof that a whole workflow is reusable. Runtime dependency checks
remain authoritative for the actual execution.

All remembered observations stay quarantined and non-executable. The recall
adapter explicitly inspects that observation area; it does not insert it into
normal trusted context or change lifecycle status. The service excludes expired
and obsoleted memories and enforces project/owner visibility.

Recall samples at most 20 records per capability, with 10 capability lookups,
up to five displayed memories per step and a 64 KiB output budget. Underlying
pool and byte omissions remain visible. Repeated unmet conditions in three
distinct sampled runs produce review candidates with episode references.
Retries of one run do not count as separate validations. These candidates are
not causal diagnoses or validated skill improvements; no automatic skill edit,
memory promotion, rule activation, model training or performance claim follows.

Each episode is at most 16,000 UTF-8 bytes. Oversized or malformed episodes are
rejected before capture writes. A memory outage does not change Conductor's
execution gates. The chosen run can finish while its memory result reports
pending ingestion and retains an archive. CLI exit 1 can therefore mean memory
capture is incomplete even when `execution.complete` is true: inspect both
results and retry capture, not the commands. An unconfigured client fails
before real execution; previews need no configuration.

Capture uses stable episode/request IDs. Retrying the same snapshot with the
same authenticated identity and visibility reuses the receipt. Preserve
`--visibility project` when retrying a project-visible capture. Partial batch capture can be
retried without duplicating earlier episodes. Forgotten keys remain blocked
by the service's tombstones. Server-side forgetting does not delete local
report archives or trajectory envelopes; include those external copies when
the user requests complete deletion.
