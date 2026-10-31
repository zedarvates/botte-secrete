# RSI and capability contracts — main reconciliation, 2026-10-31

Base: `ec85d1906cf3815116ba562e428407ebd44782c2`.
Preserved heads: PR #136 `59aa9fda3f5b7b46e014ce86036fd006ed1613c5`
and PR #134 `0bfb5a299a4f7d284d74c1f531ffa96efe7f7939`.
Both histories merge without textual conflicts. This is a partial observe-only
implementation; it does not qualify the wider RSI promotion pipeline.

## Boundary failures reproduced before correction

- Events from producers `a:b` / component `c` and `a` / component `b:c` produced
  one node with two observations and the last producer's metadata. Producer IDs
  now encode the tuple losslessly, including null versus literal `unknown`.
- A FIFO with no writer blocked the initial observer beyond the 0.4-second probe
  deadline. The probe child was explicitly terminated. The observer now opens
  nonblocking where supported, checks the descriptor is a regular file before
  reading, and refuses detected symlinked `.botte` or log paths.
- Escaped lone surrogates were accepted as kind strings but broke UTF-8 CLI
  output. Invalid field types, empty/non-UTF-8 identities, duplicate fields and
  nonfinite JSON constants now produce rejected records. Rejections break the
  adjacency chain rather than inventing a transition across missing evidence.

The rule declarations/anchors and semantic review receipts were reconciled with
these changes. The previous statement that other authority/exit modules were
absent was corrected: the RSI rules do not qualify those modules, even if present.
The underlying rule-audit engine remains unchanged from the supplied PR.

## Executed validation

- Full canonical runner: **1,760 passed, 0 failed; all 93 suites**.
- Focused RSI suite: **21 passed**; rule-engine suite: **10 passed**. These are
  included in the full total, not additional unique cases.
- Registered rules gate: three rules, score 100, zero errors, warnings,
  conflicts, unenforced rules or stale receipts. Fingerprint:
  `0a25b43858fc62c81e8826b219efc3fc82be8572782534f1bf51f976a82eed19`.
- Both JSON schemas accepted by Draft 2020-12 schema checking; a graph and a
  capability fixture validated, while an invalid capability fixture was rejected.
  The validator is a verification dependency, not a new runtime requirement.
- All **592 tracked Python files** parsed with Python 3.10 grammar under local
  Python 3.12. This is grammar evidence, not a local Python 3.10 runtime result.
- README command checks: **11 passed, 0 failed, 10 intentional skips**.
- Checkup completed: no high-severity taint candidate; the missing project-local
  MCP declaration remains environment drift. No runtime reachability was proved.
- Documentation checking remains explicitly incomplete for six existing
  multiline/blockquote constructs, rather than claiming all links were checked.
- A separate agent reviewed the raw diff, reproduced identity/FIFO/output defects
  and verified their corrections. This is not third-party certification.

Hosted checks must qualify the final published candidate before merge. Later
code changes invalidate affected behavioral evidence.

## Limits

No live homelab or model was exercised by this feature. The graph records file
adjacency, not causality or run-level dependencies. Input is bounded but not an
atomic snapshot, an I/O deadline or an OS sandbox. The rules gate checks declared
semantics and anchors; score 100 is not certification of complete implementation
bodies or proof that its referenced probes ran. The capability schema is
experimental metadata with no runtime activation.
