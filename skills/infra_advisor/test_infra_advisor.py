#!/usr/bin/env python3
"""Tests for infra_advisor — synthetic snapshots + tempfile project.

    python -m skills.infra_advisor.test_infra_advisor
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.infra_advisor.advisor import recommend, ascii_diagram, Snapshot
from skills.infra_advisor.auto_audit import duplication_scan, auto_audit


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def _snap(**kw) -> Snapshot:
    base = dict(hardware={"os": "Linux 6", "cpu_cores": 8, "ram_gb": 32,
                          "gpus": [], "vram_gb": 0},
                backends=[], cloud_keys=[], network_hosts=[], mcp_wired=True)
    base.update(kw)
    return Snapshot(**base)


def _titles(tips):
    return " | ".join(t.title for t in tips)


def main() -> int:
    state = [0, 0]
    print("== infra_advisor tests ==")

    # No GPU + no backend → P0 install + P1 add GPU.
    tips = recommend(_snap())
    _ok("no backend → P0 install local LLM",
        any(t.priority == "P0" and "local LLM" in t.title for t in tips), state)
    _ok("no GPU → recommend adding a GPU",
        any("Add a GPU" in t.title for t in tips), state)

    # Windows inference node with a chat backend → Linux migration tip.
    win = _snap(hardware={"os": "Windows 11", "cpu_cores": 32, "ram_gb": 32,
                          "gpus": ["RTX"], "vram_gb": 16},
                backends=[{"kind": "lmstudio", "chat": True, "models": ["m"],
                           "label": "LM Studio", "host": "127.0.0.1", "port": 1234}])
    wt = recommend(win)
    _ok("Windows inference node → suggest Linux/WSL2",
        any("Linux" in t.title for t in wt), state)
    _ok("16GB GPU → no 'add GPU' nag (good tier)",
        not any("Add a GPU" in t.title for t in wt), state)
    _ok("no Qdrant → recommend Qdrant", any("Qdrant" in t.title for t in wt), state)

    # MCP not wired → P1 wire tip.
    nm = recommend(_snap(mcp_wired=False))
    _ok("MCP not wired → P1 wire tip",
        any(t.category == "mcp" and t.priority == "P1" for t in nm), state)

    # vision accelerator suggested when no comfyui backend.
    _ok("no vision backend → Hailo tip",
        any("Hailo" in t.title for t in tips), state)

    # diagram renders, fixed width, contains header.
    diagram = ascii_diagram(win)
    _ok("diagram has header + box borders",
        "LOCAL CLUSTER" in diagram and diagram.startswith("┌") and "└" in diagram, state)

    # duplication scan finds identical functions across files.
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        fn = ("def compute(x):\n    total = 0\n    for i in range(x):\n"
              "        total += i * 2\n    return total\n")
        (root / "a.py").write_text(fn, encoding="utf-8")
        (root / "b.py").write_text("import os\n" + fn, encoding="utf-8")
        (root / "c.py").write_text("def unique():\n    return 42\n", encoding="utf-8")
        dup = duplication_scan(root, min_lines=4)
        _ok("duplication scan finds the cross-file dupe",
            dup["duplicate_groups"] >= 1 and dup["duplicates"][0]["count"] == 2, state)

        rep = auto_audit(root)
        _ok("auto_audit returns directives+infra+duplication+headline",
            all(k in rep for k in ("directives", "infra_tips", "duplication", "headline", "diagram")),
            state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
