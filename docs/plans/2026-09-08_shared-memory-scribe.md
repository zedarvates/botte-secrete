# ADR: Shared memory API and advisory scribe

Date: 2026-09-08. Status: implemented pilot; host deployment pending.

## Evidence and decision

The inspected `main` baseline is `7da1eaeff66aad9fe4bf0b771b58a0688c868c09`.
It already contains Memory Hub v2 (SQLite per project), source provenance,
quarantine, lifecycle and local MCP wrappers. `auto_memory` is a separate legacy
JSON memory bank. `context_budget` already supplies a deterministic selector.

Use Memory Hub v2 rather than introducing a second memory authority. Add an
authenticated shared service and an HTTP-backed stdio MCP bridge. Reuse the
existing store with an optional deferred commit so entry, receipt and revisions
participate in one transaction. Existing callers retain automatic commits.

## Scope changes from the initial architecture proposal

PostgreSQL/pgvector remains a backend target. The inspected runtime has no
PostgreSQL service, Docker executable or reachable configured homelab host.
SQLite enables an executable first contract without speculative deployment.
No database migration, model installation, cloud-model call or private corpus
ingestion is required for this pilot.

The scribe implements bounded lexical/supplied-vector nearest-neighbour advice.
It never promotes, merges, labels training data or creates permissions. A future
micro-NN needs reviewed examples and comparison against this baseline. The
existing micro-NN weights serve other tasks and are not repurposed as a scribe.

## Consequences

Authenticated agents can exchange project observations while private entries
stay owner-scoped. Corrections become versioned and remove obsolete context;
concurrent updates conflict explicitly. Quarantine remains a data/policy boundary.
The service stores quoted source data, so its directory and exports are private
operational assets, not files to commit with the toolkit.

The live-store forget operation removes history as well as current data. It
retains a minimal hashed tombstone to block replay; disconnected exports and
backups require separate reconciliation. Read snapshots avoid mixed-version
recall responses. The pilot is bounded to loopback and 16 concurrent requests.

## Validation boundary

Automated fixtures exercise real HTTP and an actual MCP subprocess against
temporary databases. They validate behavior, not semantic-model accuracy,
real-host availability, production HTTP hardening or restore procedures.
See [operator guide](../shared-memory.md) for exact commands and next gates.
