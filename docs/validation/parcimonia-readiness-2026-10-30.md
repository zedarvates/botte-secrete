# Parcimonia runtime and test readiness

Date: 2026-10-30. Prerequisite: draft PR 147 at
`cd6b605fd63ca6cb7a5c816f14289f283e5c1918`. Candidate runtime: 1.11.0.
This increment changes the local Python runtime and its guidance. The separate
cloud service remains 0.5.0 / Site version 5; these local changes are not a new
cloud deployment or public-directory publication.

## Reproduced defects and corrected behavior

| Existing input or observation | Before | Candidate |
| --- | --- | --- |
| `.mcp.json` containing `botte-llm: {}` or `null` | recognized as wired | invalid declaration |
| MCP configuration root `[]` | `AttributeError` | invalid declaration, no crash |
| Declared launcher absent from the current PATH/filesystem | wiring alone implied availability | declaration and launcher status separate; reachability not checked |
| Doctor with an unavailable machine scan | claimed active local routing | backend availability and host routing unverified |
| Runner exits 0 with `runner crashed` and no result | API and HTML PASS | incomplete, not passed |
| Runner exits 1 with `RESULT: 0 errors` | HTML PASS | API and HTML failed |
| Failed step followed by zero-error result | API and HTML PASS | failed |
| Runner absent | CLI exit 0 | not_run, CLI exit 2 |

The independent reviewer exported the immutable prerequisite revision and ran
the same probe against it and the candidate. Valid action-only and CRLF output
still pass with exit 0 and exactly one zero-error completion result. Repeated
completion markers, missing termination evidence and oversized numeric markers
cannot establish success. An omitted oversized STEP index retains its failure.

## Contract and compatibility

`mcp_wiring.status` replaces the ambiguous `wired` value with `configured`,
`missing`, `invalid`, `unreadable`, `unsupported`, `disabled`, or
`not_applicable`. Consumers of the JSON field must handle the new values.
Sources, launcher lookup basis, inspection scope and uninspected configuration
locations are explicit. The legacy private `_mcp_wired` boolean means a
recognized enabled declaration only. An existing malformed configuration remains
visible even in ephemeral PR CI; no-config CI retains `not_applicable`.

No configured command is executed and no network request is made by the static
helper. Its launcher observation uses this process's environment, not a claimed
host environment. Runtime and reachability remain `not_checked`. Hermes YAML
and Python 3.10 TOML without `tomllib` are explicitly unsupported; global and
installed-plugin configuration remain outside the project-file inspection.

`app_test` now shares its verdict between JSON and HTML. CLI exit codes are
0 passed, 1 failed, 2 incomplete/not_run. Direct HTML callers need an observed
exit code to establish a passing run. These are intentional compatibility
changes for consumers that previously treated generation as test success.

## Qualification scope

Targeted checks: 75 checkup, 11 infra, 56 app-test and 9 canonical-runner checks
passed. The distribution package checks also passed (10 checks). Python 3.10
grammar checks cover the executable changes; local execution uses Python 3.12.
Independent review added malformed launch fields, invalid URL ports, excessive
numeric markers, nonregular configuration files and inconsistent report rows.
The canonical `python scripts/run_tests.py -q` completed with **1224 passed,
0 failed across 75 suites**. A project checkup reports directives 100/100 and
the expected missing project declaration in this source checkout, with runtime
and reachability explicitly not checked. It does not qualify an installed host.

A wheel built from the candidate package sources was installed with its declared
dependencies in a fresh virtual environment. **21 isolated-install checks
passed** on Linux / Python 3.12.14, including `pip check`, package identity,
installed `botte-mcp` handshake/catalog, the real research witness, scoped plan,
installed static diagnostic and absent-runner CLI exit 2. These commands ran
outside the source checkout without injecting `PYTHONPATH` or overriding HOME.
This qualifies that runtime combination, not installation into the Codex host.
Packaged source inputs remained unchanged during build and verification.

Wheel SHA-256:
`46ae3d8a7707433a5377f1f1b4b1b9509c0a29390368c5bd7a342fe2dcf54919`.
Packaged-source manifest SHA-256:
`8ee55e3b027ef9cc1b4caa6de75dc3f86f8f0b1651d9f34a38637c7f05828741`.
README command checks: 11 passed, 0 failed, 10 intentional skips. Local links:
74 Markdown files, 0 broken. Fast staged secret/JSON/syntax checks passed;
all 11 changed Python files parse with Python 3.10 grammar.

The current environment has no detected SikuliX/OculiX runner and no desktop
display. Subprocess contract fixtures do not constitute a GUI run. Actual
application or game control, real-time performance, billed tokens, cost and
end-to-end acceleration remain unqualified. The draft video remains a captioned
preview of recorded helper outputs.
