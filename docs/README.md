# Documentation

This is the entry point for Botte Secrète's public documentation. Pages are
grouped by the reader's goal. Module-level commands and contracts remain beside
the code in `skills/<name>/SKILL.md`.

## Start here

- [Main README](../README.md) — install Botte and understand its boundaries.
- [README en français](../README.fr.md) — parcours d'installation en français.
- [Architecture](ARCHITECTURE.md) — understand layers, data flow, and trust
  boundaries.
- [Development guide](DEVELOPMENT.md) — set up a checkout, modify a capability,
  and validate changes.

## How-to guides

| Goal | Guide |
|---|---|
| Connect an MCP-compatible agent | [MCP integration](mcp-integration.md) |
| Connect Cursor or Windsurf | [Cursor and Windsurf](integrations/cursor-windsurf-mcp.md) |
| Evaluate a Hermes integration | [Hermes](integrations/hermes.md) |
| Use the Loop Optimizer safely | [Loop Optimizer](loop-optimizer.md) |
| Build and capture the public dashboard | [Dashboard capture](dashboard-capture.md) |
| Regenerate README visuals | [Documentation visuals](screenshots-plan.md) |
| Configure optional Hailo vision | [Hailo vision template](hailo-vision-example.md) |
| Run an independent strategic review | [Monte Cristo](../skills/monte_cristo/README.md) |

## Reference

| Subject | Reference |
|---|---|
| Report formats | [`schemas/`](schemas/) |
| Security reporting | [Security policy](../SECURITY.md) |
| Release history | [Changelog](../CHANGELOG.md) |

## Explanations and evidence

- [Local model benchmark note](local-model-benchmarks.md) — historical evidence
  with explicit reproducibility limits.
- [`plans/`](plans/) — proposed work and design explorations.

## Document status

- **Current reference** describes an implemented contract and should match the
  current code.
- **Dated evidence** records what a specific command or experiment observed at a
  specific time.
- **Proposal** describes unimplemented or unvalidated work.
- **Historical publication** preserves old release or social copy and must not be
  treated as current product documentation.

Files such as `x-thread-*.md`, `reddit-post-*.md`, release-candidate notes, and
dated plans are retained for provenance. Their numbers and recommendations are
not automatically current.

## Validate documentation

```bash
python scripts/test_readme_commands.py
python scripts/check_docs_links.py
python scripts/pre-commit-check.py --fast
```

The complete test count comes from `python scripts/run_tests.py -q`. Do not copy
that moving total into multiple permanent pages.
