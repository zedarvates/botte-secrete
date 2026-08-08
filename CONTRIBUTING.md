# Contributing to Botte Secrète

Thank you for helping improve Botte Secrète. Contributions are welcome for code,
tests, documentation, reproducible benchmarks, integrations, and security
hardening.

## Before opening a pull request

1. Fork the repository and create a focused branch.
2. Read the [development guide](docs/DEVELOPMENT.md) and the `SKILL.md` for the
   capability you are changing.
3. Keep the diff minimal and preserve unrelated work.
4. Add a test or reproducible validation for behavior changes.
5. Update public documentation only when the public contract changed.

```bash
python scripts/run_tests.py --changed -q
python scripts/pre-commit-check.py --fast
python scripts/check_docs_links.py
```

Run the complete suite when the change affects shared infrastructure, routing,
MCP dispatch, schemas, packaging, or multiple modules:

```bash
python scripts/run_tests.py -q
```

## Pull-request checklist

- The problem and chosen scope are explained.
- New behavior has focused tests.
- CLI and MCP declarations reach a real handler.
- Files are read and written explicitly as UTF-8.
- No credentials, local endpoints, private paths, or generated machine state are
  included.
- Performance and savings claims include a reproducible command and corpus.
- Documentation distinguishes stable behavior from experiments and plans.
- The PR lists exactly which checks were run and their result.

## Commit messages

Use a concise [Conventional Commit](https://www.conventionalcommits.org/)
subject where practical:

```text
feat(router): add bounded fallback policy
fix(mcp): connect declared tool to its handler
docs(readme): replace stale metrics with reproducible visuals
test(loader): cover read-only agent toolsets
```

## Code and documentation style

- Prefer the standard library and existing modules.
- Keep architecture flat and match the surrounding style.
- Preserve validation, error handling, security, and accessibility.
- Use English for canonical technical documentation. Keep `README.fr.md` aligned
  with material onboarding changes.
- Keep cross-module explanations in `docs/` and implementation details beside
  the module.

## Security reports

Do not open a public issue for a vulnerability. Follow the private reporting
instructions in [SECURITY.md](SECURITY.md).

For general questions, open a focused GitHub discussion or issue with enough
context to reproduce the problem and without private data.
