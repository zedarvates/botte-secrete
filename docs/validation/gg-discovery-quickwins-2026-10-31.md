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
