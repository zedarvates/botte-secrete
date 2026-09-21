# Shared memory and scribe pilot

Status: implemented pilot, opt-in. Backend: the existing SQLite Memory Hub v2.
The HTTP API and stdio MCP bridge use one service and one configured store.
No remote host has been configured by adding these files.

## What works

- Sourced capture and work checkpoints, private or shared inside an allowed project.
- Identity and rights supplied by bearer authentication, never by tool arguments.
- Atomic corrections with expected versions, history and idempotent request receipts.
- Reviewed user facts as normal context; external/agent data in explicit observation review.
- Exact-key, lexical and optional supplied-vector retrieval with model/dimension matching.
- A nearest-neighbour scribe that suggests related memories without merging or training.
- Current Markdown views for Obsidian, with remembered Markdown/HTML escaped.
- Deletion of live entries, revisions, vectors and request receipts, with replay tombstones.

No trained scribe weights are included. Embeddings are accepted from a configured
upstream encoder; this pilot does not download BGE-M3 or call any model endpoint.
Its lexical baseline and vector arithmetic use the Python standard library.

## Start a local pilot

From the repository root, using Python 3.10+ (`python` on Windows):

```bash
python -m skills.memory_hub.cli init --directory /absolute/private/memory-pilot --project pilot
python -m skills.memory_hub.cli serve --directory /absolute/private/memory-pilot --port 8766
```

`init` requires a new directory. It creates `auth.json` and two owner-only token
files without printing their contents. On Windows, restrict the directory ACL
to the account running the service before placing real data in it.

| Identity | Intended use |
|---|---|
| `worker` | Normal agent. Read, capture, correct and forget its own entries in the configured project. |
| `operator` | Trusted user ingress and lifecycle review. Its credential must stay outside model-facing tools. |

Give each additional agent a unique actor ID and token file in `auth.json`.
Projects and rights are explicit lists. Restart the service after changing
credentials or permissions. Ordinary worker tokens cannot claim `source.type=user`.
`curate` permits editing another owner's shared entry; it does not reveal private entries.

The Python API pilot binds only to loopback. Use a TLS reverse proxy or SSH
tunnel for connections from another machine. A reverse proxy must set the
upstream Host header to `127.0.0.1:8766`; browser Origins are intentionally refused.
The HTTP client verifies HTTPS, refuses redirects and accepts plaintext HTTP
only for loopback. Do not expose Python's pilot server directly on the LAN.

## Connect an MCP client to the same API

Example command/args entry; replace paths for the particular machine:

```json
{
  "mcpServers": {
    "botte-shared-memory": {
      "command": "python",
      "args": [
        "-m", "skills.memory_hub.cli", "mcp",
        "--url", "http://127.0.0.1:8766",
        "--token-file", "/absolute/private/memory-pilot/worker.secret"
      ],
      "cwd": "/absolute/path/to/botte-secrete"
    }
  }
}
```

The bridge has no database of its own. When running on another machine, point
it at the authenticated HTTPS origin or a local tunnel to the central service.
The token file belongs to that client identity. Never register the operator token
with a general-purpose agent. Existing local Memory Hub MCP entry points retain
their old behavior; do not expose them as a network authorization boundary or
write to the pilot directory through them.

## Common API contract

The exact schemas are generated from `skills/memory_hub/shared_contract.py`:

```bash
python -m skills.memory_hub.cli schema
```

The authenticated server also exposes `GET /openapi.json` and `GET /health`.
All memory operations use `POST /v1/memory/<operation>` and JSON bodies.
MCP tool names are `memory_<operation>`.

| Operation | Consequences and retry behavior |
|---|---|
| `capture`, `checkpoint` | Insert a proposal, its first revision and a receipt. An identical actor/request-ID retry returns the original receipt; different input conflicts. |
| `correct` | Require the current version; retain history, replace content, drop any old vector, and reset lifecycle review. Current recall/wiki immediately stop using the old fact. |
| `review` | Advance the existing lifecycle under a configured review right. Quarantined observations cannot be promoted or relabeled as trusted through correction. |
| `recall` | Return current reviewed user context by default. `area=observations` explicitly returns quarantined data marked non-executable. Expired/obsoleted entries are excluded. |
| `history` | Owner/curator inspection of up to 20 recent revisions, capped at 64 KiB and marked when truncated. No data mutation. |
| `scribe` | Return nearest reviewed, accessible memories as advice. No classification is declared verified; no merge, training or promotion follows. |
| `wiki` | Return a fresh Markdown string from the same read snapshot. No files or cache are created by the service. |
| `forget` | Delete entry, all revisions, vector and associated receipts. Retain only a digest of project/key and deletion time to block old capture replays. A repeated request returns `forgotten`; a new record needs a new key. |

The source excerpt is preserved verbatim alongside the record. Its digest proves
the stored excerpt's integrity, not the source author's identity or truth. URI,
evidence and subject references are not fetched or declared verified. A checkpoint
is an observation, not proof that an action succeeded. Memory never grants a
permission to act. Lifecycle review changes memory selection, not runtime authority.

For capture/correct/checkpoint, provide `project_id`, `key`, `request_id` and:

```json
{
  "record": {
    "text": "The fixture test was reported as successful.",
    "kind": "observation",
    "visibility": "project",
    "source": {
      "type": "agent",
      "id": "synthetic-message-1",
      "run_id": "synthetic-run-1",
      "observed_at": 1800000000,
      "excerpt": "The fixture test was reported as successful."
    },
    "subject_ref": "repo:example@commit-id",
    "evidence_refs": ["run:example-1"]
  }
}
```

Use the actual observation timestamp when running this example. `correct`,
`review` and `forget` additionally require `expected_version`. The service
rejects unknown fields, non-finite numbers, duplicate JSON keys and oversized input.

To use vectors, supply `embedding={"model":"encoder@revision", "vector":[...]}`
on the record and query. Pin the same encoder revision, preprocessing and
dimension for both. Vectors are advisory retrieval features and never change
provenance. Without supplied vectors, retrieval uses lexical cosine and exact
keys. It is not a claim that a neural semantic encoder was executed.

## Limits and operational boundaries

- The repository's existing quarantine contract is retained. Agent/tool/repo/web
  observations are available through explicit observation recall, not normal
  trusted context. A future verifier workflow needs its own design and evidence.
- Per request, the newest 2,000 accessible active entries are considered; truncation
  is explicit. Indexed PostgreSQL retrieval is the next scale step.
- Context budgets are measured in actual serialized UTF-8 bytes, not model tokens.
  The existing `context_budget.knapsack` selects whole entries; sources are not cut off.
- This pilot implements revision lineage, not general graph traversal or GraphRAG.
- A saved wiki export or a model's already loaded context remains an external copy.
  Deletion affects the live service; it cannot erase those copies or offline backups.
- Tombstones prevent live-store replay resurrection. Restoring an older backup can
  also restore deleted data: reconcile a current deletion ledger before reopening
  any restored store. Backup/restore automation has not been deployed.
- Local operating-system access to the database/token files is privileged access.
  Do not share SQLite/WAL files between live writers using file synchronization.
- Authenticated clients can store sensitive excerpts. Choose project scopes,
  visibility and retention deliberately. The scribe is not a secret detector.

## Acceptance and next increments

Install the optional test dependencies; the running service itself uses only
the Python standard library. CI runs these focused tests on Python 3.10–3.12
after the existing repository test runner.

```bash
python -m pip install -e '.[memory-test]'
python -m pytest --rootdir=. -q skills/memory_hub/test_shared_service.py skills/memory_hub/test_shared_transport.py skills/memory_hub/test_memory_hub.py
python -m skills.memory_hub.test_quarantine
```

Tests cover HTTP-to-MCP continuity, restart/replay, concurrent corrections,
rollback, identity spoofing, scope isolation, expiry, deletion, stale vectors,
byte budgets, safe Markdown rendering and preservation of the v2 quarantine.
Fixtures are synthetic; passing them does not validate retrieval quality on a
real homelab corpus or prove a home machine has been deployed.

Next increments, in order:

1. Run this pilot with two real machine identities and a private test project.
2. Evaluate the actual encoder and 20 held-out recall questions, including
   corrections, ambiguous names, outdated test evidence and negative results.
3. Add a storage adapter for PostgreSQL/pgvector, or reuse an operational Qdrant
   index if the host audit confirms it. Preserve these API/authorization tests.
4. Add source-backed typed relationships and invalidation of dependent summaries.
5. Build reviewed scribe labels; compare rules/k-NN to a micro-NN on chronological
   and project-separated splits. Observe recommendations before enabling any
   automatic routing. Do not self-label training data from the scribe's guesses.
