#!/usr/bin/env python3
"""Tests for report persistence — tempdir, deterministic.

    python -m skills.report.test_report
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.report import save, list_reports, to_markdown, to_html, timestamped_name

SAMPLE = {
    "project": "/x", "headline": "directives 100/100 · infra 72/100",
    "drift": ["No policy", "MCP not wired"],
    "tips": [{"priority": "P1", "title": "wire MCP"}, {"priority": "P2", "title": "qdrant"}],
    "diagram": "┌ CLUSTER ┐\n│ a · b   │\n└─────────┘",
    "cost": {"analysis_llm_tokens": 0, "always_on_tokens_per_session": 70000},
}


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def main() -> int:
    state = [0, 0]
    print("== report tests ==")

    name = timestamped_name("check up!", "md")
    _ok("timestamped name = name_YYYY-MM-DD_HHMMSS.ext",
        re.match(r"check-up_\d{4}-\d{2}-\d{2}_\d{6}\.md$", name) is not None, state)

    md = to_markdown("Checkup", SAMPLE)
    _ok("markdown has title + timestamp", md.startswith("# Checkup") and "Generated" in md, state)
    _ok("markdown renders list-of-dicts as a table", "| priority | title |" in md, state)
    _ok("markdown renders ASCII diagram as code block", "```\n┌ CLUSTER ┐" in md, state)

    htmltxt = to_html("Checkup", SAMPLE)
    _ok("html is self-contained with the data",
        "<h1>Checkup</h1>" in htmltxt and "<table>" in htmltxt and "<pre>" in htmltxt, state)

    with tempfile.TemporaryDirectory() as d:
        paths = save("checkup", SAMPLE, fmt="both", out_dir=Path(d))
        _ok("save writes both md + html, timestamped",
            len(paths) == 2 and all(re.search(r"_\d{4}-\d{2}-\d{2}_\d{6}\.(md|html)$", p) for p in paths),
            state)
        rows = list_reports(Path(d))
        _ok("list_reports finds the saved reports",
            len(rows) == 2 and rows[0]["name"] == "checkup", state)
        _ok("html-only save writes one file",
            len(save("metrics", SAMPLE, fmt="html", out_dir=Path(d))) == 1, state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
