#!/usr/bin/env python3
"""Tests for security_scanner — patterns, AST, scanner, report, CLI.

    python -m skills.security_scanner.test_security_scanner
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.security_scanner.patterns import PATTERNS, PATTERN_MAP, Severity, Pattern
from skills.security_scanner.ast_checker import analyze_ast
from skills.security_scanner.scanner import scan_file, scan_dir
from skills.security_scanner.report import Finding, ScanReport, scan_report


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def _make_dangerous_py() -> str:
    """Create a temporary Python file with known dangerous patterns."""
    d = tempfile.mkdtemp(prefix="secscan_")
    p = Path(d) / "dangerous.py"
    p.write_text('''"""Dangerous test file."""

import os
import subprocess
import base64

# Eval
def bad_eval(user_input):
    result = eval(user_input)  # danger

# Exec
def bad_exec(code):
    exec(code)  # danger

# Subprocess shell
def bad_shell(filepath):
    subprocess.run(f"rm {filepath}", shell=True)  # danger

# OS system
def bad_system(cmd):
    os.system(cmd)  # danger

# Base64 decode
def bad_decode(data):
    return base64.b64decode(data)  # potential obfuscation

# Hardcoded key
API_KEY = "sk-1234567890abcdef1234567890abcdef"

# Write to system path
def bad_write():
    open("/etc/passwd", "w").write("hacked")  # danger

# Environment leak
def bad_leak():
    print(os.environ["API_KEY"])  # danger
''')
    return str(p)


def _make_clean_py() -> str:
    """Create a clean Python file with no dangerous patterns."""
    d = tempfile.mkdtemp(prefix="secscan_clean_")
    p = Path(d) / "clean.py"
    p.write_text('''"""Clean test file."""

import pathlib
import hashlib
import json
from typing import Optional

def safe_process(data):
    """Process data safely."""
    result = json.dumps(data)
    return result

def safe_hash(content):
    """Use SHA-256 (not broken)."""
    return hashlib.sha256(content).hexdigest()

def safe_write(path, data):
    """Write to pathlib managed path."""
    p = pathlib.Path(path)
    p.write_text(data)

class Calculator:
    def add(self, a, b):
        return a + b
''')
    return str(p)


def main() -> int:
    state = [0, 0]
    print("== security_scanner tests ==")

    # ── Pattern database ──
    _ok("PATTERNS is not empty", len(PATTERNS) > 0, state)
    _ok("All patterns have unique names",
        len(PATTERNS) == len(set(p.name for p in PATTERNS)), state)
    _ok("All patterns have valid severity",
        all(p.severity in Severity for p in PATTERNS), state)
    _ok("PATTERN_MAP has all patterns",
        len(PATTERN_MAP) == len(PATTERNS), state)
    _ok("critical patterns exist",
        any(p.severity == Severity.CRITICAL for p in PATTERNS), state)
    _ok("eval_call pattern is critical",
        PATTERN_MAP["eval_call"].severity == Severity.CRITICAL, state)

    # ── Scan dangerous file ──
    dpath = _make_dangerous_py()
    findings = scan_file(dpath, do_ast=True)
    _ok("dangerous.py produces findings",
        len(findings) > 0, state)

    # Check specific findings
    pattern_names = [f.pattern for f in findings]
    _ok("detects eval_call",
        "eval_call" in pattern_names, state)
    _ok("detects exec_call",
        "exec_call" in pattern_names, state)
    _ok("detects subprocess_shell",
        "subprocess_shell" in pattern_names, state)
    _ok("detects os_system",
        "os_system" in pattern_names, state)
    _ok("detects base64_decode",
        "base64_decode" in pattern_names, state)
    _ok("detects open_write_critical",
        "open_write_critical" in pattern_names, state)
    _ok("detects print_environ",
        "print_environ" in pattern_names, state)

    # Check severity correctness
    for f in findings:
        if f.pattern == "eval_call":
            _ok("eval_call has critical severity",
                f.severity == "critical", state)
            break

    # ── Scan clean file ──
    cpath = _make_clean_py()
    clean_findings = scan_file(cpath, do_ast=True)
    _ok("clean.py produces minimal findings",
        len(clean_findings) < 2, state)  # permit false positives from broad patterns

    # ── AST analysis ──
    with open(dpath) as f:
        source = f.read()
    ast_findings = analyze_ast(source, dpath)
    ast_names = [f["pattern"] for f in ast_findings]
    _ok("AST detects eval_call",
        "eval_call" in ast_names, state)
    _ok("AST detects subprocess_shell",
        "subprocess_shell" in ast_names, state)
    _ok("AST detects open_write_critical",
        "open_write_critical" in ast_names, state)

    # ── Report ──
    report = scan_report(findings)
    _ok("report.count matches findings",
        report.count == len(findings), state)
    _ok("report.by_severity has all keys",
        all(k in report.by_severity for k in ["critical", "error", "warning", "info"]),
        state)
    _ok("compact() is non-empty for findings",
        len(report.compact()) > 0, state)
    _ok("to_json() includes summary",
        '"summary"' in report.to_json(), state)
    _ok("markdown() includes header",
        'Security Scan' in report.markdown(), state)

    # ── Empty report ──
    empty = scan_report([])
    _ok("empty report.count == 0",
        empty.count == 0, state)
    _ok("empty report.markdown() says clean",
        "Clean" in empty.markdown(), state)

    # ── Finding dataclass ──
    f = Finding(file="test.py", line=42, column=5, pattern="eval_call",
                severity="critical", snippet='eval(user_input)')
    _ok("Finding has expected attributes",
        f.file == "test.py" and f.severity == "critical", state)

    # ── scan_dir on clean dir ──
    clean_dir = str(Path(cpath).parent)
    clean_scan = scan_dir(clean_dir, fail_on="critical")
    _ok("clean dir scan returns findings or empty",
        isinstance(clean_scan, list), state)

    # ── fail_on severity filter: keep findings AT LEAST AS SEVERE ──
    with tempfile.TemporaryDirectory() as fd:
        (Path(fd) / "mix.py").write_text(
            "import hashlib\nhashlib.md5(b'x')\neval(user_input)\n", encoding="utf-8")
        errplus = {f.severity for f in scan_dir(fd, fail_on="error")}
        _ok("fail_on=error keeps critical, drops warning",
            "critical" in errplus and "warning" not in errplus, state)
        allsev = {f.severity for f in scan_dir(fd, fail_on="info")}
        _ok("fail_on=info returns every severity (incl. critical + warning)",
            "critical" in allsev and "warning" in allsev, state)
        crit_only = {f.severity for f in scan_dir(fd, fail_on="critical")}
        _ok("fail_on=critical keeps only critical",
            crit_only == {"critical"} if crit_only else True, state)

    # ── Edge: nonexistent path ──
    missing = scan_dir("/nonexistent/path/xyz")
    _ok("nonexistent path returns error finding",
        len(missing) == 1 and missing[0].pattern == "not_found", state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
