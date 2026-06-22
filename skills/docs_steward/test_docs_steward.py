#!/usr/bin/env python3
"""Tests for docs_steward — scoped documentation map.

    python -m skills.docs_steward.test_docs_steward
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.docs_steward import (build_map, detect_components, render_index,
                                 write_indexes, INDEX_FILENAME, INDEX_MARKER)


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def _fixture(root: Path) -> None:
    (root / "README.md").write_text("# Project\n" + "x" * 400, encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "architecture.md").write_text("# Arch\n" + "y" * 800, encoding="utf-8")
    (root / "report.html").write_text("<html>human</html>", encoding="utf-8")
    # server: manifest component
    (root / "server").mkdir()
    (root / "server" / "pyproject.toml").write_text("[project]\nname='s'\n", encoding="utf-8")
    (root / "server" / "main.py").write_text("print(1)\n", encoding="utf-8")
    (root / "server" / "README.md").write_text("# Server\n" + "z" * 600, encoding="utf-8")
    # client: manifest component
    (root / "client").mkdir()
    (root / "client" / "package.json").write_text('{"name":"c"}', encoding="utf-8")
    (root / "client" / "index.js").write_text("console.log(1)\n", encoding="utf-8")
    (root / "client" / "guide.md").write_text("# Client\n" + "w" * 200, encoding="utf-8")
    # tools: known-name (convention) component
    (root / "tools").mkdir()
    (root / "tools" / "helper.py").write_text("def h(): pass\n", encoding="utf-8")
    # parser: code-only dir, name not in the known set → kind "dir"
    (root / "parser").mkdir()
    (root / "parser" / "lex.py").write_text("def lex(): pass\n", encoding="utf-8")
    (root / "parser" / "notes.md").write_text("# Parser\n" + "p" * 100, encoding="utf-8")
    # an ignored / non-component dir
    (root / "scripts").mkdir()
    (root / "scripts" / "build.sh").write_text("echo hi\n", encoding="utf-8")


def main() -> int:
    state = [0, 0]
    print("== docs_steward tests ==")

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _fixture(root)

        comps = {c.name: c for c in detect_components(root)}
        _ok("detects server/client/tools/parser as components",
            {"server", "client", "tools", "parser"} <= set(comps), state)
        _ok("non-component dirs (scripts/docs) are excluded",
            "scripts" not in comps and "docs" not in comps, state)
        _ok("manifest components are tagged 'manifest'",
            comps["server"].kind == "manifest" and comps["client"].kind == "manifest", state)
        _ok("known-name component is tagged 'convention'", comps["tools"].kind == "convention", state)
        _ok("code-only component is tagged 'dir'", comps["parser"].kind == "dir", state)

        m = build_map(root)
        cmap = {c["name"]: c for c in m["components"]}

        global_paths = {g["path"] for g in m["global_docs"]}
        _ok("root README + docs/ are global",
            "README.md" in global_paths and "docs/architecture.md" in global_paths, state)
        _ok("server/README.md is scoped to the server component",
            any(x["path"] == "server/README.md" for x in cmap["server"]["local_docs"]), state)
        _ok("a component's local docs exclude other components' docs",
            all("client/" not in x["path"] for x in cmap["server"]["local_docs"]), state)

        _ok("html is classified as human audience",
            any(g["audience"] == "human" and g["fmt"] == "html" for g in m["global_docs"]), state)
        _ok("linked globals are LLM-facing only (no html)",
            all(not p.endswith(".html") for p in cmap["server"]["linked_globals"]), state)

        _ok("scoped load is cheaper than all project docs",
            cmap["server"]["scoped_tokens"] < m["total_doc_tokens"], state)
        _ok("map is JSON-serialisable", isinstance(json.dumps(m), str), state)

        # rendered index
        idx = render_index(cmap["server"], root)
        _ok("index carries the stable marker", INDEX_MARKER in idx, state)
        _ok("index lists the component's local doc", "README.md" in idx, state)
        _ok("index links a global doc with a relative path",
            "../README.md" in idx or "..\\README.md" in idx, state)

        # write_indexes: dry-run writes nothing; --write creates DOCS.md
        preview = write_indexes(root, dry_run=True)
        _ok("dry-run writes nothing to disk",
            not (root / "server" / INDEX_FILENAME).exists()
            and all(not r["written"] for r in preview), state)
        write_indexes(root, dry_run=False, only="server")
        _ok("write creates the component DOCS.md",
            (root / "server" / INDEX_FILENAME).exists(), state)
        _ok("only the requested component is written",
            not (root / "client" / INDEX_FILENAME).exists(), state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
