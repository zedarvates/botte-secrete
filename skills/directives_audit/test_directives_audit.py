#!/usr/bin/env python3
"""Tests for directives_audit — uses tempfile so it runs anywhere.

    python -m skills.directives_audit.test_directives_audit
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.directives_audit import audit, discover, validate


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def _sev_for(findings, needle):
    return [f for f in findings if needle in f["message"]]


def main() -> int:
    state = [0, 0]
    print("== directives_audit tests ==")

    # A. Empty project → missing-instructions crit finding.
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "app.py").write_text("print(1)", encoding="utf-8")
        rep = audit(d)
        _ok("empty project flags missing instructions",
            not rep["has_instructions"] and _sev_for(rep["findings"], "No agent-instruction"),
            state)
        _ok("empty project score < 70", rep["score"] < 70, state)

    # B. Rich project → detect formats + each finding type.
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "src").mkdir()
        (root / "src" / "main.py").write_text("x=1", encoding="utf-8")
        (root / "app.py").write_text("x=1", encoding="utf-8")
        # instruction with one good + one broken reference
        (root / "CLAUDE.md").write_text(
            "Read `src/main.py` and `ghost/missing.py`.", encoding="utf-8")
        (root / "AGENTS.md").write_text("Use `app.py`.", encoding="utf-8")
        # HTML instruction
        (root / "CLAUDE.html").write_text(
            "<html><body><h1>Hi</h1></body></html>", encoding="utf-8")
        # oversized always-on instruction
        (root / ".windsurfrules").write_text("word " * 6000, encoding="utf-8")
        # intent + spec + ADR (markdown and HTML)
        (root / "CONTEXT.md").write_text("# Context\nWhy.", encoding="utf-8")
        (root / "specs").mkdir()
        (root / "specs" / "api.md").write_text("# Spec", encoding="utf-8")
        (root / "docs" / "adr").mkdir(parents=True)
        (root / "docs" / "adr" / "0001.html").write_text(
            "<p>decision</p>", encoding="utf-8")

        files = discover(root)
        paths = {f.path for f in files}
        _ok("discovers CLAUDE.md/AGENTS.md/.windsurfrules",
            {"CLAUDE.md", "AGENTS.md", ".windsurfrules"} <= paths, state)
        _ok("discovers nested spec + ADR (md & html)",
            "specs/api.md" in paths and "docs/adr/0001.html" in paths, state)
        _ok("detects HTML format",
            any(f.path == "CLAUDE.html" and f.fmt == "html" for f in files), state)

        findings = [f.to_dict() for f in validate(root, files)]
        _ok("flags HTML instruction file", _sev_for(findings, "is HTML"), state)
        _ok("flags oversized instruction (.windsurfrules)",
            any("large" in f["message"] and f["path"] == ".windsurfrules" for f in findings),
            state)
        _ok("flags broken ref ghost/missing.py",
            any("ghost/missing.py" in f["message"] for f in findings), state)
        _ok("does NOT flag valid refs src/main.py or app.py",
            not any("src/main.py" in f["message"] or "app.py" in f["message"]
                    for f in findings if "not found" in f["message"]), state)
        _ok("notes multiple instruction sources",
            _sev_for(findings, "Multiple instruction sources"), state)
        _ok("has_instructions True when present", audit(root)["has_instructions"], state)

    # C. Config files don't produce phantom path refs.
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "AGENTS.md").write_text("ok", encoding="utf-8")
        (root / ".mcp.json").write_text(
            '{"x":"WebFetch(domain:api.github.com)","y":"application/vnd.github+json"}',
            encoding="utf-8")
        findings = [f.to_dict() for f in validate(root)]
        _ok("config JSON not scanned for broken refs",
            not any("not found" in f["message"] for f in findings), state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
