#!/usr/bin/env python3
"""Tests for skill_finder — synthetic catalog so results are deterministic.

    python -m skills.skill_finder.test_skill_finder
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.skill_finder import load_catalog, rank, find


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def _mkskill(root: Path, name: str, body: str, fm_desc: str = "") -> None:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    front = f"---\nname: {name}\ndescription: {fm_desc}\n---\n" if fm_desc else ""
    (d / "SKILL.md").write_text(front + body, encoding="utf-8")


def main() -> int:
    state = [0, 0]
    print("== skill_finder tests ==")

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _mkskill(root, "postgres-optimizer",
                 "# Postgres\nTune slow SQL queries, indexes, EXPLAIN ANALYZE.",
                 fm_desc="Optimize slow PostgreSQL queries and indexes.")
        _mkskill(root, "react-components",
                 "# React\nBuild React UI components, hooks, JSX.",
                 fm_desc="Create React frontend components.")
        _mkskill(root, "docker-deploy",
                 "Containerize and deploy apps with Docker and compose.")  # no frontmatter

        cat = load_catalog([root])
        _ok("catalog loads all 3 (incl. no-frontmatter one)", len(cat) == 3, state)
        _ok("frontmatter description parsed",
            any(s.name == "postgres-optimizer" and "PostgreSQL" in s.description for s in cat),
            state)
        _ok("no-frontmatter skill gets a body summary",
            any(s.name == "docker-deploy" and s.description for s in cat), state)

        # relevance
        top = rank("optimize slow postgres SQL queries", cat, top_k=3)
        _ok("postgres query → postgres-optimizer ranks #1",
            top and top[0].skill.name == "postgres-optimizer", state)

        top2 = rank("build a frontend UI in react", cat, top_k=3)
        _ok("react query → react-components ranks #1",
            top2 and top2[0].skill.name == "react-components", state)

        top3 = rank("containerize and deploy with docker", cat, top_k=3)
        _ok("docker query → docker-deploy ranks #1 (body-only match works)",
            top3 and top3[0].skill.name == "docker-deploy", state)

        # irrelevant query → low/no matches
        none = rank("xyzzy quantum banana teleport", cat)
        _ok("irrelevant query → no matches", len(none) == 0, state)

        res = find("optimize postgres", roots=[root], top_k=2)
        _ok("find() reports 0 cloud tokens", res["cloud_tokens"] == 0, state)
        _ok("find() returns matches list", len(res["matches"]) >= 1, state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
