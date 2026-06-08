# Fallow-Like Implementation Plan — Botte Secrète

> **For Hermes:** Implement task-by-task. Each task = 2-5 min. TDD where applicable.

**Goal:** Build a comprehensive, multi-language codebase analysis engine (fallow-like) that covers dead code, duplication, complexity, architecture boundaries, feature flags, runtime ingestion, hot paths, blast radius, with CLI/CI/MCP/VS Code integration and JSON/SARIF/markdown output.

**Architecture:** Python 3.12 + tree-sitter (multi-language AST) + networkx (graph analysis) + typer (CLI) + rich (terminal output) + pydantic (data models). stdlib-first. No heavy frameworks. Modular design — each analyzer is a plugin.

**Tech Stack:** Python 3.12, tree-sitter, networkx, typer, rich, pydantic, grep-ast. Optional: semgrep for security patterns.

**Constraints:**
- stdlib-first (already satisfied by chosen stack)
- No file > 1500 lines
- Each module = one responsibility
- All output in English
- CLI via typer, not click

---

## Phase 1 — Core Engine (Tasks 1-8)

### Task 1: Project structure + data models
### Task 2: AST scanner (tree-sitter)
### Task 3: Dead code analyzer
### Task 4: Duplication analyzer
### Task 5: Complexity analyzer
### Task 6: Architecture boundaries analyzer
### Task 7: Feature flag analyzer
### Task 8: Secrets analyzer (API keys + exports)

## Phase 2 — Runtime + Graph Analysis (Tasks 9-11)

### Task 9: Dependency graph builder (networkx)
### Task 10: Runtime ingestion
### Task 11: Hot paths + Blast radius analyzer

## Phase 3 — Output Formats (Tasks 12-14)

### Task 12: Output formatters (JSON, SARIF, Markdown)
### Task 13: Health score calculator
### Task 14: Trends + History + Alerts

## Phase 4 — CLI + CI + MCP + VS Code (Tasks 15-18)

### Task 15: CLI (typer)
### Task 16: CI integration (GitHub Actions + pre-commit)
### Task 17: MCP server
### Task 18: VS Code extension scaffold

## Phase 5 — Monorepo + Local Workflows (Tasks 19-20)

### Task 19: Monorepo support
### Task 20: Local workflow definitions

## Phase 6 — Integration + Push (Task 21)

### Task 21: Integrate into botte-secrete repo and push

---

## Feature Checklist

- [x] Dead code analysis
- [x] Duplication detection
- [x] Complexity and health
- [x] Architecture boundaries
- [x] Static feature flag detection
- [x] CLI, CI, VS Code, MCP
- [x] JSON, SARIF, markdown output
- [x] Monorepo local workflows
- [x] Continuous runtime ingestion
- [x] Hot paths, blast radius, and importance
- [x] Runtime-backed health
- [x] Shared history and trends
- [x] Alerts
- [x] Runtime-aware PR and review signals
- [x] API keys and exports

## File Manifest

```
skills/fallow-like/
├── __init__.py
├── models.py              # Pydantic data models
├── config.py              # Configuration (pydantic-settings)
├── scanner.py             # Multi-language AST scanner (tree-sitter)
├── graph_builder.py       # Dependency graph (networkx)
├── health.py              # Health score calculator
├── cli.py                 # CLI (typer + rich)
├── monorepo.py            # Monorepo support
├── analyzers/
│   ├── dead_code.py       # Dead code detection
│   ├── duplication.py     # Token-based duplication
│   ├── complexity.py      # Cyclomatic + nesting
│   ├── boundaries.py      # Architecture boundary violations
│   ├── feature_flags.py   # Static feature flag detection
│   ├── secrets.py         # API keys, passwords, tokens
│   ├── hot_paths.py       # Runtime hot path analysis
│   └── blast_radius.py    # Change impact analysis
├── outputs/
│   ├── json_formatter.py  # JSON output
│   ├── sarif_formatter.py # SARIF output (CodeQL compatible)
│   └── markdown_formatter.py # Markdown report
├── runtime/
│   ├── ingestion.py       # Runtime data ingestion
│   └── trends.py          # Trend tracking + alerts (SQLite)
└── integrations/
    ├── github_action.yml  # GitHub Actions workflow
    ├── pre-commit.sh      # Pre-commit hook
    ├── mcp_server.py      # MCP server (stdio JSON-RPC)
    └── vscode/            # VS Code extension
        ├── package.json
        └── extension.ts
```
