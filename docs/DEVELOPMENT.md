# Development guide

This guide is for contributors changing Botte Secrète itself. For a first
installation, start with the [README](../README.md).

## Set up a development checkout

Requirements: Python 3.10 or newer and Git. On Windows, use `python` rather than
`python3`.

```bash
git clone https://github.com/zedarvates/botte-secrete.git
cd botte-secrete
python -m venv .venv
python -m pip install -e .
```

Activate the virtual environment with the command appropriate for your shell,
then run a targeted validation:

```bash
python scripts/run_tests.py --changed -q
python scripts/pre-commit-check.py --fast
```

## Design principles

- **Stdlib first.** Add a dependency only when the standard library and current
  dependencies cannot provide a clear, safe implementation.
- **Flat packages.** Each capability normally lives under `skills/<name>/`.
- **Validation is not optional.** Do not remove input checks, error handling,
  security controls, or accessibility to save code or tokens.
- **Local-first is not trust-first.** Local models and LAN endpoints still need
  verification, authentication, and bounded input.
- **Claims need evidence.** Public performance, test, or readiness claims must
  point to a reproducible command or dated artifact.
- **Preserve user state.** Never replace unrelated MCP configuration, dirty Git
  changes, or project-specific integrations.

## Python and console conventions

Always specify UTF-8 for file operations:

```python
from pathlib import Path

text = Path("example.txt").read_text(encoding="utf-8")
Path("copy.txt").write_text(text, encoding="utf-8")
```

Scripts that print emoji or box-drawing characters must call
`skills.console_utf8.force_utf8()` before producing output. This is required for
Windows consoles that otherwise default to legacy encodings.

Match the surrounding code style. Prefer explicit data shapes and compact JSON
schemas from `docs/schemas/` for inter-agent reports.

## Add or change a capability

1. Inspect the affected call path and reuse an existing module when possible.
2. Keep the implementation under `skills/<name>/`.
3. Add or update `SKILL.md` with the module contract and safe commands.
4. Add a focused test beside the module.
5. Wire public entry points deliberately: top-level CLI, MCP schema and dispatch,
   bootstrap, or dashboard as applicable.
6. Update cross-module documentation only when the system view changed.
7. Run targeted tests, then the broader suite justified by the change.

For CLI or MCP changes, trace the complete path from declared command or tool
schema to dispatch handler and implementation. A listed tool without a handler
is a broken public contract.

## Tests

| Scope | Command |
|---|---|
| Files changed since the last commit | `python scripts/run_tests.py --changed -q` |
| Complete repository runner | `python scripts/run_tests.py -q` |
| Pytest suites | `python -m pytest --rootdir=. -q` |
| One stdlib-style module suite | `python -m skills.<module>.test_<module>` |
| Fast pre-commit checks | `python scripts/pre-commit-check.py --fast` |
| README command safety | `python scripts/test_readme_commands.py` |
| Local documentation links | `python scripts/check_docs_links.py` |

Report targeted validation as targeted. Do not call the full suite green unless
the complete runner printed its final success summary.

## Documentation and visuals

Documentation follows a simple division:

- `README.md` and `README.fr.md`: GitHub onboarding and product boundaries;
- `docs/`: cross-module explanations and task-oriented guides;
- `skills/<name>/SKILL.md`: authoritative module reference;
- `docs/integrations/`: task-oriented integration guides;
- `docs/plans/`: proposals, not current product contracts;
- `CHANGELOG.md`: release history.

Regenerate the benchmark chart and deterministic routing capture with:

```bash
python scripts/generate_docs_visuals.py
```

Build the sanitized public dashboard artifact with:

```bash
python scripts/generate_public_dashboard.py
```

Screenshots for public documentation must come from sanitized public artifacts
or fixtures. Do not capture API keys, private paths, local memory content,
machine identifiers, or proprietary project data.

After documentation changes, verify relative Markdown links and run the README
command test. Moving totals should come from a generated snapshot rather than
being copied into several files.

## Generated and machine-specific files

Do not commit machine-specific configuration such as `configs/llm-endpoints.json`,
`.mcp.json`, private compressor stores, local event ledgers, or `.botte-cache/`.
Review `git status` before committing because the repository may contain work
from another agent or developer.

## Release preparation

1. Confirm the intended version in `pyproject.toml` and `CHANGELOG.md`.
2. Run the complete test runner and pre-commit checks.
3. Regenerate public visuals if their underlying data changed.
4. Check README commands, documentation links, package contents, and CI files.
5. Review `git diff` for secrets and machine-specific artifacts.
6. Create a signed, reviewable commit and publish through the normal pull-request
   workflow.

Publishing a branch, tag, package, release, or external announcement requires
explicit authorization; local validation alone is not a published release.
