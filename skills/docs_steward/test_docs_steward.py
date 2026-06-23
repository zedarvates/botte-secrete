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
                                 write_indexes, INDEX_FILENAME, INDEX_MARKER,
                                 scan_tasks, prune_all, report_hygiene,
                                 archive_reports, lifecycle_report)


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


def _lifecycle_tests(state):
    print("\n== docs_steward lifecycle tests ==")
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        # a mixed task file + a fully-done plan
        (root / "TODO.md").write_text(
            "# TODO\n- [ ] open one\n- [x] done one\n- [x] done two\nnotes\n",
            encoding="utf-8")
        (root / "PLAN-old.md").write_text(
            "# Old plan\n- [x] shipped a\n- [x] shipped b\n", encoding="utf-8")
        # a README with an all-done checklist is NOT a plan → must be left alone
        (root / "README.md").write_text(
            "# Project\n- [x] roadmap item shipped\n- [x] another shipped\n", encoding="utf-8")
        # .botte reports: 4 for 'checkup', 2 for 'audit'
        rep = root / ".botte" / "reports"
        rep.mkdir(parents=True)
        for stamp in ("2026-06-01_100000", "2026-06-02_100000",
                      "2026-06-03_100000", "2026-06-04_100000"):
            (rep / f"checkup_{stamp}.md").write_text("x", encoding="utf-8")
        for stamp in ("2026-06-01_110000", "2026-06-02_110000"):
            (rep / f"audit_{stamp}.md").write_text("y", encoding="utf-8")

        tasks = {t.path: t for t in scan_tasks(root)}
        _ok("scan_tasks finds the mixed TODO with right counts",
            tasks["TODO.md"].open_tasks == 1 and tasks["TODO.md"].done_tasks == 2, state)
        _ok("a fully-done plan is flagged fully_done + is_plan",
            tasks["PLAN-old.md"].fully_done and tasks["PLAN-old.md"].is_plan, state)
        _ok("a README with a checklist is NOT treated as a plan",
            not tasks["README.md"].is_plan, state)
        _ok("done items carry a token-waste estimate",
            tasks["TODO.md"].done_tokens > 0, state)
        _ok("reports under .botte are not treated as task files",
            all(".botte" not in p for p in tasks), state)

        # prune dry-run changes nothing
        prune_all(root, dry_run=True)
        _ok("prune dry-run leaves files untouched",
            "[x] done one" in (root / "TODO.md").read_text(encoding="utf-8")
            and (root / "PLAN-old.md").exists(), state)

        # prune for real: strip done from TODO, archive fully-done plan
        prune_all(root, dry_run=False)
        todo_after = (root / "TODO.md").read_text(encoding="utf-8")
        _ok("prune strips done items but keeps open ones",
            "open one" in todo_after and "done one" not in todo_after, state)
        _ok("removed items are preserved in an archive file (not lost)",
            (root / ".botte" / "archive" / "TODO.done.md").exists(), state)
        _ok("a fully-done plan is moved out of the working tree",
            not (root / "PLAN-old.md").exists()
            and (root / ".botte" / "archive" / "PLAN-old.md").exists(), state)
        _ok("a non-plan README is never pruned or archived",
            (root / "README.md").exists()
            and "roadmap item shipped" in (root / "README.md").read_text(encoding="utf-8"), state)

        # report hygiene: keep 2 per name → archive 2 checkups
        hy = report_hygiene(root, keep=2)
        _ok("report_hygiene keeps N most recent per name",
            len(hy["keep"]) == 4 and len(hy["archive"]) == 2, state)
        _ok("the archived reports are the oldest checkups",
            all(r["name"] == "checkup" for r in hy["archive"]), state)

        archive_reports(root, keep=2, dry_run=True)
        _ok("report archive dry-run moves nothing",
            not (rep / "archive").exists(), state)
        moved = archive_reports(root, keep=2, dry_run=False)
        _ok("report archive moves the older files",
            len(moved) == 2 and (rep / "archive").exists(), state)

        lr = lifecycle_report(root, keep=2)
        _ok("lifecycle_report is JSON-serialisable + has both sections",
            isinstance(json.dumps(lr), str)
            and "tasks" in lr and "reports" in lr, state)


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

    _lifecycle_tests(state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
