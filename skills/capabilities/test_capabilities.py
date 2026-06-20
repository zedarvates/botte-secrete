#!/usr/bin/env python3
"""Tests for the capability registry / curator.

    python -m skills.capabilities.test_capabilities
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.capabilities import load, ascii_map, curate, by_layer, LAYERS


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def main() -> int:
    state = [0, 0]
    print("== capabilities tests ==")

    caps = load()
    names = {c.name for c in caps}
    _ok("loads the repo's skills", len(caps) >= 20, state)
    _ok("known skills present + layered",
        any(c.name == "app_test" and c.layer == "ACT" for c in caps)
        and any(c.name == "bootstrap" and c.layer == "DEPLOY" for c in caps), state)
    _ok("every capability has a valid layer",
        all(c.layer in LAYERS for c in caps), state)
    _ok("cloud-capable flag set (auto_router escalates)",
        any(c.name == "auto_router" and not c.local_capable for c in caps), state)

    grouped = by_layer(caps)
    _ok("by_layer groups across SENSE/ACT/DEPLOY",
        grouped["SENSE"] and grouped["ACT"] and grouped["DEPLOY"], state)

    m = ascii_map(caps)
    _ok("ascii map names every layer present",
        all(ly in m for ly in ("SENSE", "DECIDE", "ACT", "REMEMBER", "GOVERN", "DEPLOY")), state)

    top = curate("test my desktop app and capture crashes")
    _ok("curator ranks app_test first for a GUI-test goal",
        top and top[0]["name"] == "app_test", state)
    top2 = curate("write documentation for my module")
    _ok("curator ranks docgen for a docs goal",
        any(c["name"] == "docgen" for c in top2[:3]), state)

    # layer override via frontmatter
    with tempfile.TemporaryDirectory() as d:
        s = Path(d) / "myskill"; s.mkdir()
        (s / "SKILL.md").write_text(
            "---\nname: myskill\nlayer: GOVERN\ndescription: x\n---\nbody", encoding="utf-8")
        caps2 = load(Path(d))
        _ok("frontmatter layer: overrides the map",
            caps2 and caps2[0].layer == "GOVERN", state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
