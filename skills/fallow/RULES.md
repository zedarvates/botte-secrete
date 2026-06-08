# Fallow — Codebase Intelligence

> Static analysis for JS/TS projects. CLI Rust, zero dependencies.

## Installation

```bash
cargo install fallow-cli
```

## Commands

```bash
# Global health
fallow health --score --hotspots

# Dead code detection
fallow dead-code --production

# Duplication
fallow dupes --mode semantic

# Circular dependencies
fallow cycles

# PR risk analysis
fallow risk --diff changes.patch

# JSON export
fallow health --score --format json
```

## Score Interpretation

| Score | Grade | Meaning |
|-------|-------|---------|
| 90-100 | A | Healthy |
| 70-89 | B | Good |
| 50-69 | C | Acceptable |
| 30-49 | D | Fragile |
| 0-29 | F | Critical |

## Python Companion

```bash
python3 scripts/fallow-python.py /path/to/project --format text
```

## Full Audit (JS + Python)

```bash
./scripts/fallow-audit.sh /path/to/project /tmp/reports
```

## Pitfalls

- `--production`: Ignores dev dependencies. Use for deployment audits.
- `--score`: Requires `package.json` or `tsconfig.json`.
- PR risk: Compare with target branch: `fallow risk --base main --head feature`
- Large projects: Fallow is fast (~ Rust). ~2s for 150K lines.
