#!/usr/bin/env python3
"""Tests for the project deployer — tempfile projects, no network needed.

    python -m skills.bootstrap.test_bootstrap
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.bootstrap import setup, wire_mcp


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def main() -> int:
    state = [0, 0]
    print("== bootstrap (deployer) tests ==")

    # 1. Fresh project: setup writes .mcp.json, .botte/config.json, report.
    with tempfile.TemporaryDirectory() as d:
        proj = Path(d)
        (proj / "app.py").write_text("print(1)", encoding="utf-8")
        rep = setup(proj)
        mcp = json.loads((proj / ".mcp.json").read_text(encoding="utf-8"))
        _ok("botte-llm registered in .mcp.json",
            "botte-llm" in mcp.get("mcpServers", {}), state)
        _ok("MCP entry runs skills.llm_mcp.server",
            mcp["mcpServers"]["botte-llm"]["args"] == ["-m", "skills.llm_mcp.server"], state)
        _ok(".botte/config.json written", (proj / ".botte" / "config.json").exists(), state)
        _ok("setup-report.json written", (proj / ".botte" / "setup-report.json").exists(), state)
        _ok("report knows skill catalog size", rep["skill_catalog_size"] > 0, state)
        # enforcement layer: policy committed + preflight hook wired
        _ok("policy .botte/policy.md written", (proj / ".botte" / "policy.md").exists(), state)
        settings = json.loads((proj / ".claude" / "settings.json").read_text(encoding="utf-8"))
        _ok("preflight hook wired in settings.json",
            "skills.preflight.hook" in json.dumps(settings), state)

    # 2. Non-destructive merge: keep an existing MCP server.
    with tempfile.TemporaryDirectory() as d:
        proj = Path(d)
        (proj / ".mcp.json").write_text(
            json.dumps({"mcpServers": {"other": {"command": "x", "args": []}}}),
            encoding="utf-8")
        wire_mcp(proj)
        mcp = json.loads((proj / ".mcp.json").read_text(encoding="utf-8"))
        _ok("existing MCP server preserved", "other" in mcp["mcpServers"], state)
        _ok("botte-llm added alongside", "botte-llm" in mcp["mcpServers"], state)

    # 3. Idempotent: re-running doesn't duplicate.
    with tempfile.TemporaryDirectory() as d:
        proj = Path(d)
        wire_mcp(proj); wire_mcp(proj)
        mcp = json.loads((proj / ".mcp.json").read_text(encoding="utf-8"))
        _ok("re-run is idempotent (one botte-llm)",
            list(mcp["mcpServers"]).count("botte-llm") == 1, state)

    # 4. --create-agents-md scaffolds when no instructions exist.
    with tempfile.TemporaryDirectory() as d:
        proj = Path(d)
        (proj / "app.py").write_text("x=1", encoding="utf-8")
        setup(proj, create_agents_md=True)
        _ok("AGENTS.md scaffolded for instruction-less project",
            (proj / "AGENTS.md").exists(), state)
        # And not clobbered on a project that already has one.
        before = (proj / "AGENTS.md").read_text(encoding="utf-8")
        setup(proj, create_agents_md=True)
        _ok("existing AGENTS.md not overwritten",
            (proj / "AGENTS.md").read_text(encoding="utf-8") == before, state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
