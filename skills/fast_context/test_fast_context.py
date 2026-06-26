#!/usr/bin/env python3
"""Tests for fast_context — exploration repo déterministe.

    python -m skills.fast_context.test_fast_context
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.fast_context.agent import explore, discover_query_type, QueryType
from skills.fast_context.readers import fast_read, fast_glob, fast_grep
from skills.fast_context.ranker import score, rank_results
from skills.fast_context.compiler import compile_report, format_compact, format_markdown
from skills.fast_context.store import LRUCache


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def _make_test_project() -> str:
    """Crée un petit projet test temporaire."""
    d = tempfile.mkdtemp(prefix="fastcontext_test_")
    root = Path(d)

    # src/main.py
    (root / "src").mkdir()
    (root / "src/__init__.py").write_text("")
    (root / "src/main.py").write_text("""\"\"\"Main module.\"\"\"

import sqlite3
import json
from pathlib import Path

DATABASE = "test.db"

def connect():
    \"\"\"Connect to database.\"\"\"
    return sqlite3.connect(DATABASE)

def query(sql):
    \"\"\"Execute a query.\"\"\"
    conn = connect()
    return conn.execute(sql).fetchall()

class Database:
    def __init__(self, path):
        self.path = path

    def open(self):
        return sqlite3.connect(self.path)
""")

    # tests/test_main.py
    (root / "tests").mkdir()
    (root / "tests/__init__.py").write_text("")
    (root / "tests/test_main.py").write_text("""\"\"\"Tests for main module.\"\"\"

from src.main import connect, query, Database

def test_connect():
    conn = connect()
    assert conn is not None

def test_query():
    result = query("SELECT 1")
    assert len(result) > 0

def test_database_open():
    db = Database(":memory:")
    assert db.open() is not None
""")

    # scripts/deploy.py (avec pattern security)
    (root / "scripts").mkdir()
    (root / "scripts/__init__.py").write_text("")
    (root / "scripts/deploy.py").write_text("""\"\"\"Deploy script.\"\"\"
import os
import subprocess

def deploy(env):
    os.system(f"deploy --env {env}")
    subprocess.run("deploy.sh", shell=True)

def cleanup():
    eval("os.remove('/tmp/old')")
""")

    # config.toml
    (root / "config.toml").write_text("""[project]
name = "test-project"
version = "1.0.0"

[dependencies]
sqlite3 = "*"
""")

    return str(root)


def main() -> int:
    state = [0, 0]
    print("== fast_context tests ==")

    # ── discover_query_type ──
    _ok("'find imports' → IMPORTS",
        discover_query_type("find all imports") == QueryType.IMPORTS, state)
    _ok("'understand function connect' → FUNCTION",
        discover_query_type("understand function connect()") == QueryType.FUNCTION, state)
    _ok("'where are the tests' → TESTS",
        discover_query_type("where are the tests?") == QueryType.TESTS, state)
    _ok("'search for sqlite3' → PATTERN",
        discover_query_type("search for sqlite3 usage") == QueryType.PATTERN, state)
    _ok("'audit security eval' → SECURITY",
        discover_query_type("audit security eval usage") == QueryType.SECURITY, state)
    _ok("unknown query falls back to PATTERN",
        discover_query_type("something completely random") == QueryType.PATTERN, state)

    # ── readers ──
    _ok("fast_read returns correct lines",
        len(fast_read(__file__)) > 0, state)
    _ok("fast_read returns [] for missing file",
        fast_read("/nonexistent/file.py") == [], state)
    _ok("fast_read skips binary files",
        fast_read("/usr/bin/ls") == [], state)

    # ── fast_glob ──
    root = _make_test_project()
    py_files = fast_glob("*.py", root)
    _ok("fast_glob finds .py files",
        len(py_files) > 0, state)
    _ok("fast_glob skips __pycache__",
        all("__pycache__" not in f for f in py_files), state)

    # ── fast_grep ──
    matches = fast_grep("import", root)
    _ok("fast_grep finds imports",
        len(matches) > 0, state)
    _ok("fast_grep result has file/line/text",
        all(k in matches[0] for k in ["file", "line_num", "text"]), state)

    sec = fast_grep(r"eval\s*\(", root)
    _ok("fast_grep security finds eval(",
        any("eval(" in m["text"] for m in sec), state)

    # ── ranker ──
    sc1 = score("import sqlite3", "import sqlite3", "src/main.py", 1)
    sc2 = score("import sqlite3", "class Something:", "src/other.py", 50)
    _ok("exact match scores higher than unrelated",
        sc1 >= sc2, state)
    _ok("score is in [0, 1]",
        0.0 <= sc1 <= 1.0, state)

    dummy = [{"file": "a.py", "line_num": 1, "text": "import x"},
             {"file": "b.py", "line_num": 1, "text": "def f():"}]
    ranked = rank_results(dummy, "import")
    _ok("rank_results sorts by score descending",
        ranked[0]["score"] >= ranked[-1]["score"], state)

    # ── compiler ──
    dummy_compiled = compile_report(dummy, "import")
    _ok("compile_report returns list",
        isinstance(dummy_compiled, list), state)
    _ok("compile_report result has file/snippet/type/score",
        all(k in dummy_compiled[0] for k in ["file", "snippet", "type", "score"]), state)

    compact = format_compact(dummy_compiled, "import test")
    _ok("format_compact includes query",
        "import test" in compact, state)

    md = format_markdown(dummy_compiled, "import test")
    _ok("format_markdown includes header",
        "FastContext" in md, state)

    # ── store ──
    cache = LRUCache(maxsize=3, ttl=60)
    cache.put("k1", "v1")
    cache.put("k2", "v2")
    _ok("cache.get returns value",
        cache.get("k1") == "v1", state)
    _ok("cache.get missing returns None",
        cache.get("kx") is None, state)
    cache.put("k3", "v3")
    cache.put("k4", "v4")
    _ok("cache evicts LRU",
        cache.size == 3, state)
    cache.invalidate("k2")
    _ok("cache invalidate removes key",
        cache.get("k2") is None, state)
    cache.invalidate()
    _ok("cache full invalidate clears all",
        cache.size == 0, state)

    # ── Integration: explore ──
    results = explore(root, "find imports")
    _ok("explore returns results for 'find imports'",
        len(results) > 0, state)
    _ok("explore results have file:snippet:type:score",
        all(k in results[0] for k in ["file", "snippet", "type", "score"]), state)
    _ok("explore finds at least one import type",
        any(r["type"] == "import" for r in results), state)

    results_fn = explore(root, "understand function: connect")
    _ok("explore 'function' finds defs",
        len(results_fn) > 0, state)

    results_tests = explore(root, "where are the tests?")
    _ok("explore 'tests' finds test files",
        len(results_tests) > 0, state)
    _ok("explore 'tests' has test-type results",
        any(r["type"] == "test" for r in results_tests), state)

    results_sec = explore(root, "audit security")
    _ok("explore 'security' finds dangerous patterns",
        len(results_sec) > 0, state)

    results_pattern = explore(root, "search for sqlite3")
    _ok("explore 'pattern' finds sqlite3",
        len(results_pattern) > 0, state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
