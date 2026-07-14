# Release candidate v1.9.0rc1

## Included

- robustness fixes for CLIs, caches, compression, context, and event tracking;
- a deterministic, controllable, observable Loop Optimizer;
- an optional, fail-closed Needle tool-router experiment;
- startup documentation and loop MCP commands.

## Verification performed on July 14, 2026

| Check | Result |
|---|---:|
| `python scripts/run_tests.py` | 688 passed, 0 failed |
| `python -m pytest --rootdir=. -q` | 109 passed |
| `python scripts/pre-commit-check.py --fast` | passed |
| `python -m skills.checkup.cli .` | passed; historical security findings tracked separately |

## Safe defaults

The controller ships in observation mode:

```text
BOTTE_LOOP_OPTIMIZER=shadow
BOTTE_NEEDLE_ROUTER=0
```

The release is immediately usable for local audits and telemetry. It enables
neither a Needle model nor a learned policy.

## Requirements before stable activation

1. collect 2,000 real, verified Botte transitions;
2. demonstrate at least 10% fewer average tokens without reducing success;
3. validate Needle locally: tool accuracy ≥95%, valid arguments ≥98%, zero
   dangerous false routes, and p95 below the local LLM;
4. roll out at 10%, 50%, then 100%, with 100 regression-free scenarios at
   every stage.

## Publication checklist

Before publishing, review the diff, exclude `.claude/` and `.codex/` local
workspace files, create tag `v1.9.0rc1`, and publish artifacts from a clean
environment.
