#!/usr/bin/env python3
"""Tests for the taint / data-flow security analyzer.

    python -m skills.fallow_like.test_taint
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.console_utf8 import force_utf8
from skills.fallow_like.analyzers.taint import TaintAnalyzer
from skills.fallow_like.models import TaintFinding

force_utf8()


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def _scan(code: str, language: str = "python", path: str = "x.py"):
    return SimpleNamespace(files=[SimpleNamespace(
        language=language, source=code.encode("utf-8"), path=path)])


def _run(code: str):
    return TaintAnalyzer().analyze(_scan(code))


def _has(findings, cwe: str) -> bool:
    return any(f.cwe == cwe for f in findings)


def main() -> int:
    state = [0, 0]
    print("== taint analyzer tests ==")

    # 1. command injection: tainted input concatenated into os.system
    f = _run("import os, sys\n"
             "name = sys.argv[1]\n"
             "os.system('echo ' + name)\n")
    _ok("command injection (sys.argv → os.system) flagged CWE-78", _has(f, "CWE-78"), state)
    _ok("findings are TaintFinding with security tags",
        all(isinstance(x, TaintFinding) and "security" in x.tags for x in f), state)

    # 2. eval of tainted input → CWE-94
    f = _run("expr = input('> ')\n"
             "eval(expr)\n")
    _ok("eval(input()) flagged CWE-94", _has(f, "CWE-94"), state)

    # 3. subprocess shell=True with a dynamic command → insecure by default
    f = _run("import subprocess\n"
             "def run(cmd):\n"
             "    subprocess.run('ls ' + cmd, shell=True)\n")
    _ok("subprocess(shell=True, dynamic) flagged CWE-78", _has(f, "CWE-78"), state)

    # 4. yaml.load without SafeLoader → insecure by default (no taint needed)
    f = _run("import yaml\n"
             "data = yaml.load(open('f.yml'))\n")
    _ok("yaml.load without SafeLoader flagged CWE-502", _has(f, "CWE-502"), state)
    f_safe = _run("import yaml\n"
                  "data = yaml.load(open('f.yml'), Loader=yaml.SafeLoader)\n")
    _ok("yaml.load with SafeLoader is NOT flagged", not _has(f_safe, "CWE-502"), state)

    # 5. pickle.loads of tainted bytes → CWE-502
    f = _run("import pickle, os\n"
             "blob = os.environ['DATA']\n"
             "pickle.loads(blob)\n")
    _ok("pickle.loads(tainted) flagged CWE-502", _has(f, "CWE-502"), state)

    # 6. SQL: f-string query → CWE-89 (string-built query smell)
    f = _run("def get(cur, uid):\n"
             "    cur.execute(f'SELECT * FROM u WHERE id={uid}')\n")
    _ok("SQL via f-string flagged CWE-89", _has(f, "CWE-89"), state)

    # 7. SQL: tainted value in query → CWE-89, higher confidence
    f = _run("import sys\n"
             "def get(cur):\n"
             "    uid = sys.argv[1]\n"
             "    cur.execute('SELECT * FROM u WHERE id=' + uid)\n")
    sqlf = [x for x in f if x.cwe == "CWE-89"]
    _ok("SQL with tainted value flagged CWE-89", bool(sqlf), state)
    _ok("tainted SQL has higher confidence than a bare dynamic string",
        bool(sqlf) and sqlf[0].confidence >= 0.8, state)

    # 8. clean code: constant command + parameterised query → no findings
    f = _run("import os\n"
             "os.system('ls -la')\n"
             "def get(cur, uid):\n"
             "    cur.execute('SELECT * FROM u WHERE id=?', (uid,))\n")
    _ok("clean code (constant cmd + parameterised query) → no findings",
        len(f) == 0, state)

    # A tainted environment does not make a fixed argv command injectable.
    f = _run("import os, subprocess\n"
             "subprocess.run(['python', '-V'], env=os.environ)\n")
    _ok("fixed subprocess argv with inherited env is not command injection",
        not _has(f, "CWE-78"), state)

    # An f-prefix without interpolation is still a constant SQL statement.
    f = _run("def init(cur):\n"
             "    cur.execute(f'CREATE TABLE cache (id INTEGER)')\n")
    _ok("constant f-prefixed SQL is not reported as dynamic",
        not _has(f, "CWE-89"), state)

    # 9. non-Python files are skipped (data flow is Python-only for now)
    f = TaintAnalyzer().analyze(_scan("system(userInput);", language="c", path="x.c"))
    _ok("non-Python files are skipped", len(f) == 0, state)

    # 10. no double-counting between module scope and function scope
    f = _run("import os, sys\n"
             "def h():\n"
             "    x = sys.argv[1]\n"
             "    os.system(x)\n")
    _ok("a sink inside a function is reported exactly once",
        len([x for x in f if x.cwe == "CWE-78"]) == 1, state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
