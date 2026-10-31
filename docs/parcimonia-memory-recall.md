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
