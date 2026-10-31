# Recall verification observations with documentary sources

`botte verify recall` searches the bounded, sanitized content of verification
receipts written by the [verification memory bridge](parcimonia-verification-memory.md).
The existing Memory Hub search matches keys, categories and tags; this command
also matches the receipt's reported domain, outcome and documentary references.
It returns source versions and report digests alongside the observations so the
caller can decide what to inspect next.

Detailed failure signatures, issue prose and arbitrary report text are not part
of this searchable projection. Use the cited original report for those details.

This is a local deterministic retrieval adapter. It does not fetch a wiki, call
a model, create an embedding index, execute remembered content or add quarantine
records to the normal context bundle. The existing Memory Hub lifecycle and
schema remain unchanged.

## Read an explicitly selected store

Close or checkpoint the Memory Hub writer first. Recall accepts only an existing
project database without an active WAL or rollback journal. It opens an immutable
read-only SQLite connection and refuses an active or changing database rather
than ignoring committed WAL contents. It does not initialize MemoryStore, create
directories, migrate a schema, prune expired records or update access counters.

```sh
botte verify recall --memory-dir /explicit/memory-directory \
  --project demo-project --query "intermittency failure"
```

Only the bridge's private `parcimonia-verification` observations for the selected
project and agent can be returned. Other Memory Hub assets are outside this
adapter's scope. The agent ID is a local caller selector, not an authenticated
identity or a security sandbox for an untrusted process with filesystem access.

Each result is non-executable, unverified data. Identity, exact source version,
declared raw report SHA-256 and documentary references travel with the sanitized
summary. The original report is not retained in quarantine, so recall cannot
rehash its bytes or authenticate a supplied result. Checksums and metadata checks
detect inconsistencies; they do not prove that the report is true.

## Compare declared source versions

To check a receipt against versions selected by the caller, supply a bounded
JSON array:

```json
[{"uri":"repo:example/test-run","version":"candidate-2"}]
```

```sh
botte verify recall --memory-dir /explicit/memory-directory \
  --project demo-project --query "intermittency" \
  --current-sources current-sources.json
```

Comparison means equality or mismatch against that declaration. Without a
matching declaration, source freshness is unknown. A matching version does not
establish current software correctness, an authentic report or a verified
documentary relationship. Old failures remain reported failures when retrieved.

When `sha256` is supplied in `current-sources.json`, the source reference compares
the exact raw report UTF-8 digest, while a documentary reference compares the
caller's declared document digest. This field is not a source-code commit hash.

## Review the recalled documents against an inventory

To join recall with the existing documentary-link reviewer, supply an explicit
`parcimonia.knowledge-inventory/v1` snapshot:

```sh
botte verify recall --memory-dir /explicit/memory-directory \
  --project demo-project --query "intermittency" --inventory inventory.json
```

```json
{
  "schema":"parcimonia.knowledge-inventory/v1",
  "completeness":"complete",
  "nodes":[{"id":"doc/test-recipe","kind":"document",
            "source_uri":"repo:docs/test-recipe.md","source_version":"v3"}],
  "links":[]
}
```

With this option, output uses the separate
`parcimonia.verification-memory-linked-retrieval/v1` schema. Plain recall retains
its existing v1 schema. The wrapper preserves the original retrieval status and
coverage, reported failures, source versions, report digests, documentary
references and quarantine labels. It checks selected receipts only; omitted or
unread receipts remain outside its documentary review.

| Supplied documentary identity | Reference review |
| --- | --- |
| One document or recipe node with the exact URI and version | Declared reference resolved |
| One eligible URI candidate with a different version | Version mismatch |
| Several plausible node IDs | Ambiguous; no automatic choice |
| URI absent from an inventory declared complete | Missing in that declared inventory |
| URI absent from a partial or unknown inventory | Unknown reference |
| URI appears only under an ineligible node kind | Kind mismatch |

URI matching is exact. Lexical similarity does not create a documentary
relationship. A declared match does not verify document contents, freshness or
the truth of the receipt. Existing `current-sources` comparisons stay visible;
explicit version or digest mismatches also remain findings even when the
selected inventory matches the old reference.

`inventory_review` separately reports the supplied graph's existing links and
dependency cycles through `review_knowledge_links`. Receipt references are not
inserted as synthetic nodes or graph edges. This does not crawl a wiki or
materialize inferred relationships. Both supplied snapshots remain unchanged.

Linked output requires an 8192-byte minimum output allowance. The final compact
ASCII JSON envelope is capped, including copied retrieval and graph details.
Trimming keeps explicit counts, coverage and input digests; omitted rows cannot
produce a completed review. Exit codes are 0 for a completed scoped review,
1 for findings and 2 for incomplete, unavailable or invalid input. These codes
describe documentary review, not passing software tests.

To read the referenced bytes, use the
[local document-context adapter](parcimonia-document-context.md) with saved recall
output, an explicit file catalog/root and raw content pins. It preserves upstream
uncertainty while returning cited lexical excerpts; it does not call a model.

## Bound the read

The CLI exposes `--max-rows`, `--max-input-bytes`, `--max-results`,
`--max-output-bytes` and `--max-seconds`. Queries are lexical hints, not SQL.
Databases over 64 MiB are refused before opening. Python 3.11 and later also
apply a 1 MiB SQLite value limit; Python 3.10 relies on the database ceiling and
bounded projection checks. Time and SQLite work guards are cooperative, not an
OS memory or execution sandbox for a hostile database or filesystem writer.
Selection is deterministic within the inspected snapshot; it makes no semantic
recall or whole-corpus coverage guarantee. Raw process output and arbitrary
nested payload strings are excluded from the searchable projection.

The versioned result distinguishes a completed scoped read, an incomplete read,
and an unavailable store. A completed read can legitimately have no matches.
Omitted results and capped coverage stay explicit; an incomplete read is not
proof of absence. Exit code 0 means the bounded read completed, not that the
retrieved reports passed. Incomplete, unavailable and invalid requests return 2.

The adapter works with receipts produced by the six
[verification workflows](parcimonia-verification-workbench.md). It does not
activate the separate Parcimonia local-LLM retrieval route or synchronize a
private SavoirWiki corpus. See the
[knowledge inventory](parcimonia-knowledge-inventory.md) for those boundaries.
