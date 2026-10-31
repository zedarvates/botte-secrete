# Cited request preparation — 2026-10-31

## Revision and accepted behavior

Based on main `4cec74fb12c918bcac6967ce84054e5dafda80b9`, tree
`2e3fc8982ebff9a7e74b80b23778174dc674e89b`. The complete 1212-blob snapshot,
tree and signed commit identity were verified before modification. PR 161 was
already merged; its 20 published checks succeeded at original head
`79f3fa13c768058f70c805ef6f23f601bc061ea4`. No merge occurred in this increment.

`botte verify answer-request` consumes the existing document-context contracts
and returns `parcimonia.grounded-request/v1`. Only `ready` contains data in
`chat_kwargs`; incomplete, finding-bearing, unavailable, malformed, empty or
over-budget evidence abstains without a request. The mapping matches the
existing `LocalLLMClient.chat` signature; the client is not instantiated.

Fixed instructions remain separate from question/source JSON. Citation IDs bind
URI/version, raw-file hash, excerpt hash and exact bounds. Typed document limits,
coverage, partial-line flags, reported outcomes and known contradictions are
retained. The function takes an owned snapshot and checks internal consistency;
it neither authenticates a caller report nor independently rereads source files.

## Executed checks

| Check | Observed result |
| --- | --- |
| Canonical runner | 2284 passed, 0 failed; all 126 suites selected |
| New helper and real CLI cases | 19 passed: 14 authored helper tests and 5 command integrations |
| Independent final review | 59 targeted checks passed, 0 failures; no remaining blocker in scope |
| Installed wheel outside checkout | 28 behavioral checks passed; import isolation separately asserted; declared requirements and pip check clean |
| Python 3.10 grammar | 5 changed/new Python files parsed; local execution used Python 3.12 |
| Committed rules and checkup | Rules 100/100, 3 rules/0 findings; directives 100/100; project-local MCP declaration absent, global/plugin reachability not inferred |
| Documentation | No broken links reported; explicitly incomplete scanner coverage for 11 pre-existing unsupported Markdown constructs |

Optional external-source qualifications remain skipped when their explicit
checkouts are unavailable. Skipped qualifications are excluded from the
workbench's pass count. New tests and installed checks use public repository
documents and authored local-file/SQLite receipts only.

Independent review found internally impossible citations that could still be
prepared: a line beyond the known line count, and a shifted/far column beyond
declared/input-byte bounds. Consistency guards and regression witnesses corrected
these before final qualification. Probes also covered malformed snapshots,
hidden upstream uncertainty, stable IDs under ordering changes, escaped Unicode,
source/request/output caps, and source instructions confined to user JSON.
Purity guards denied file/network/process/client/discovery entry points during
preparation. Signature binding inspected the chat interface without calling it.

## Effects, dependencies and handoff

Selection: a pure preparer fits this step because source reading already has its
own bounded contract. It excludes inference, backend discovery, synchronization,
answer verification and semantic evidence-sufficiency assessment. No app-test
effect sidecar was available; source inspection and executed checks establish
the stated scope rather than a new authorization or declaration.

Observed effects: source code/tests/docs changed, test fixtures and package
artifacts were written outside the checkout, and the CLI read selected input
JSON and printed its result. Preparation itself changed no source/store/runtime
state and performed no model/network call. Preparation started no model or
service; local verification processes completed. No whole-host process inventory
is claimed. Remote draft-PR CI is separate from these local results.

Dependency gate: the next consumer requires `ready` and the complete request
mapping. Abstention has no mapping to replay. Before a later invocation, verify
the selected runtime, task authorization, source applicability and actual budgets.
An interrupted preparation can be repeated against the same input/question;
matching digests identify the input, not a previous inference or a current source.
Model execution is a distinct operation requiring its own result and evidence.

Reuse: these tests support deterministic request preparation for the recorded
contracts only. They do not qualify answer quality, citation accuracy, resistance
to prompt injection, a workstation model, remote transport or source truth.
No measured speed/token/cost/quality gain or generalized reuse is claimed.

## Artifact identity

Helper SHA-256:
`56a0c7ebc9289474d793029131596b5154791cb6f8c9168bb42b3dcf5a320c54`.

Wheel SHA-256:
`f8bd0e1a6fe9617f44f47f244dd2f131166cab22d507ea6a7666ff58201ce2b1`.

Packaged-input manifest SHA-256:
`b3188b4a9612c17b4832ca81f0a0d8128c7bb9b5d5a6743dcfae5a3451c45750`.

All 772 actual `skills/*` wheel inputs matched source and installed files. The
previously qualified isolated dependency environment was reused; the final wheel
was built from a scratch source copy with the available builder, reinstalled and
executed outside checkout without PYTHONPATH/HOME overrides. This was not a new
fresh-environment installation. See the
[request guide](../parcimonia-grounded-request.md).
