---
name: bootstrap
description: Deploy Botte Secrète's token-saving stack into a target project — wire the botte-llm MCP server into .mcp.json, audit the project's agent directives, and write a .botte config + setup report. Use when the user wants to "install botte", "set up token savings on a project", reduce an existing project's token/cost usage, or onboard a repo to local-first routing. This is the capstone that makes the toolkit actually save money on real projects.
---

# bootstrap — deploy the toolkit into a project

The whole point of Botte Secrète is to make *real projects* cheaper to work on.
This installs the stack into any project in one command.

## Run it

```bash
python -m skills.bootstrap.cli /path/to/project
python -m skills.bootstrap.cli /path/to/project --create-agents-md   # scaffold AGENTS.md if missing
python -m skills.bootstrap.cli /path/to/project --scan-subnet --json
```

## What it does (idempotent)

1. **Discover local backends** (`llm_backends`) so routing has somewhere to send work.
2. **Wire MCP** — merges the `botte-llm` server into the project's `.mcp.json`
   (non-destructive; keeps any existing servers). The project's agent then gains:
   `auto_route`, `local_chat`, `fusion`, `find_skills`, `audit_local_usage`,
   `route_task`, `discover_backends`, `list_models`.
3. **Audit directives** (`directives_audit`) — reports the CLAUDE.md/AGENTS.md
   health; with `--create-agents-md`, scaffolds a starter `AGENTS.md` when none exists.
4. **Write `.botte/config.json`** — chosen local model, detected cloud keys,
   token budget, routing mode (`auto`).
5. **Write `.botte/setup-report.json`** + print a summary with next steps.

## Result

The project's agent now routes cheap work (classification, extraction, summaries,
tool/skill search) to **local models for 0 cloud tokens**, escalates only the hard
parts to the cloud (`auto_router`), and picks tools with `find_skills` instead of
reading every skill description with the expensive model.

`.mcp.json` and `.botte/` hold per-machine absolute paths, so they are gitignored
in this repo — deploy on each machine.

Related: [[llm_mcp]] (the tools wired in), [[auto_router]], [[skill_finder]],
[[directives_audit]], [[llm_backends]].
