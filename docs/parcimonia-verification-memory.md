# Verification memory and documentary links

This local candidate connects the [verification workbench](parcimonia-verification-workbench.md)
to the existing [Memory Hub boundary](memory-quarantine.md). It adds neither a
corpus store nor an automatic change to normal context, wiki or LLM routing.

## Preview and explicit persistence

```sh
botte verify memory --input report.json --project example --run-id run-17 --source-uri urn:verification:run-17 --source-version REVIEWED_SOURCE_VERSION
```

Preview opens no Memory Hub. `report_sha256` covers exact supplied UTF-8 bytes,
including layout and line endings; `--source-digest` can require that hash.
`--documents` accepts explicit `{uri,version,sha256?}` references. Sources,
versions, timestamps and links remain caller declarations, not authenticated
evidence or source-freshness checks.

Exactly six helper schemas are mapped. Unknown versions and the authored demo
aggregate are rejected; supply each individual helper report. A demo passing
because it detects a seeded failure must not become an application-success fact.
The bounded projection keeps statuses, failures/context, category counts,
selected attention items, omissions and scope limits. Reduced inputs, output
tails, mutation source and full conformance payloads are excluded.

To write, add both `--write-quarantine` and
`--memory-dir /explicit/local/review-memory`. There is no implicit default-store
write. Existing MemoryStore storage and lifecycle are unchanged: tool-origin,
private, proposed, non-executable quarantine observations, excluded from normal
`context_bundle`. Use existing `review_quarantine` for explicitly labeled data;
promotion remains blocked.

For a bounded content search with source versions and report digests, use the
[read-only recall command](parcimonia-memory-recall.md) on a closed or
checkpointed project database. Missing, incomplete and unavailable reads remain
distinct; retrieved observations remain quarantined and unverified.

Identity binds project/run, source URI/version, exact report digest and document
references. Atomic SQLite lookup/write prevents duplicate versions/access writes
under competing connections. Conflicting or lifecycle-modified entries are not
overwritten. The adapter uses current MemoryStore v2 internals and refuses a
caller-owned transaction. Preview/stored/already-present exits 0; invalid input,
digest mismatch or storage conflict exits 2. Zero means a prepared/stored
observation, not a verified fact or deployed capability.

## Review documentary dependencies

Use `botte verify knowledge-links --input inventory.json` or the lazy local MCP
tool `review_knowledge_links`, whose argument is `{inventory_json:"..."}`:

```json
{
  "schema":"parcimonia.knowledge-inventory/v1",
  "completeness":"complete",
  "nodes":[
    {"id":"receipt/login","kind":"receipt","source_uri":"urn:receipt:login","source_version":"r1"},
    {"id":"recipe/login","kind":"recipe","source_uri":"repo:docs/login.md","source_version":"v7"}
  ],
  "links":[
    {"source":"receipt/login","target":"recipe/login","kind":"documents","source_version":"r1","target_version":"v7"}
  ]
}
```

Node kinds: capability, recipe, task, document, receipt. Link kinds: documents,
depends_on, evidence_for, related_to. Exact IDs and versions are checked. An
absent target is missing only relative to an inventory declared complete;
otherwise it stays unknown. Current resolved depends_on edges alone enter
bounded cycle review; a UI state graph may legitimately contain cycles.

Lexical suggestions never become resolved evidence. Counts, omissions,
depth/output limits and completeness declarations remain visible. No URI is
fetched and no content written. MCP annotations are read-only, non-destructive,
idempotent and closed-world. This Python-runtime tool is not automatically
deployed to the separate cloud service. CLI exits: 0 completed supplied-reference
review, 1 findings, 2 incomplete. Completed does not establish documentary truth,
live freshness or global dependency coverage.

## Reproduce and locate prior work

The [roundtrip example](../examples/parcimonia_memory_roundtrip.py) consumes a
supplied authored six-case demo and an explicit source version. It requires a
fresh output directory outside the repository, stores six individual receipts
in new SQLite storage, and checks dedupe, quarantine, review and declared links.
Injected missing/stale links remain separate known test witnesses. Supplied
report contents are not authenticated by this test.

See the [source-pinned knowledge inventory](parcimonia-knowledge-inventory.md)
for existing wiki, RAG/DAG, graph and local-LLM components. The separate Parcimonia
episode format still requires its own adapter; this connection targets Memory
Hub and activates no live wiki or model route.
