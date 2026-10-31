# GG-inspired bounded discovery — 31 October 2026

Base: Botte Secrète `83f5fd2368dda35c163e97ef94f5baf036ebc68c`
(draft PR #157). This candidate extends that branch without merging it.
Scope: existing local MCP lazy discovery; no new router, backend probe, GPU
work, cloud deployment or model activation.

## Behavior

- Exact tool identifiers precede lexical matches; equal scores use stable names.
- Accent normalization matches supplied lexical metadata without translation.
- Full schemas fit a cumulative compact UTF-8 byte budget; deferred names remain
  discoverable and smaller subsequent schemas may still fit.
- Description prefixes and query/result counts are bounded. Returned schemas
  cannot mutate registry definitions.
- Bad discovery arguments return a tool error while subsequent requests work.

## Validation

- Canonical changed runner: 391 passed, 0 failed across all 10 selected suites.
  This is a scoped run, not the complete repository suite.
- New budget/discovery suite: 12 tests passed, including real registered-tool
  catalog, exact boundaries, Unicode bytes, order independence and MCP errors.
- Existing lazy suite: 33 checks passed; Parcimonia contracts: 53 passed.
  These targeted runs overlap the canonical count and are not added to it.
- An actual stdio subprocess received an invalid `top_k`, returned `isError`,
  and then answered a ping; exit 0. No model/backend used.
- Four Python files parsed with Python 3.10 grammar under Python 3.12.14;
  no Python 3.10 runtime is qualified by that parse.
- Checkup completed. Project-local MCP wiring is absent; no working model
  connection, Codex host loading or Odin execution is inferred.
- Wheel build succeeded; package imports and discovery separately checked outside
  checkout as described by the PR validation record.

## Measurements and limits

Six authored queries over the actual registered catalog compared old/new compact
JSON response bytes. Results respectively: memory 2755/2914, route 2727/3162,
verify 491/620, security 1358/1636, compress 609/740, docs 936/1142.
New diagnostic fields increase these responses; this sample proves no size
saving. Three query rankings changed because registration-order ties now use
names. This is not a relevance-quality benchmark.

The default schema budget was not exhausted by those six queries. Deliberately
oversized-schema regressions exercise the refusal boundary. Schema bytes are
not total response bytes, provider tokens, billed cost or task quality.
The host must resolve deferred schemas before constructing calls. A catalog
entry does not establish backend readiness or successful execution.

Source inspiration and usage are documented in `docs/mcp-integration.md`.
No upstream code is copied. Full-list compatibility and dispatch remain in place.

## Continuation: optional compact index

The initial remote head `20dbd11d4c1c804a697eb915c0e3b5ec1cfb33c2`
completed all three observed workflows successfully (CI, PR checkup, RC1 report
reproduction). That is evidence for the preceding candidate, not this update.

The continuation adds an explicit `detail=index` projection. Default schema
lookup remains unchanged; the index preserves ranking and identifiers while
omitting schemas and shortening marked description hints. The caller must
resolve a selected exact name before constructing a tool call.

Canonical changed runner: 177 passed, 0 failed across all seven selected suites.
The discovery suite now has 19 tests, including index/default compatibility,
every registered identifier's complete schema recovery, Unicode bounds,
invalid-mode protocol errors and proof that index mode never serializes schemas.
Counts overlap; they are not additive. This is not a full repository run.

The committed `gg-discovery-index-2026-10-31.json` was measured through an actual
stdio subprocess. It includes both lookups' request/response bytes and source
SHA-256 values. Six authored queries total 12559 bytes for default lookup and
11013 for index plus selected schema (12.31% reduction). Four of six regress in
size. Selection is the first ranked result, not a validated task decision. Initial
tool listing, host context, tokens, latency and provider billing are excluded.
No tool from the returned catalog is executed by this measurement.

The index is opt-in. These results do not support global activation or a claim
of improved task quality. No model/backend/worker connection is qualified.
