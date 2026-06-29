"""ast_checker — Python AST-based static analysis for security patterns.

Utilise le module `ast` (stdlib) pour analyser le code Python
et détecter des patterns malveillants avec plus de précision que
les regex seules (moins de faux positifs pour eval/exec statiques).
"""

from __future__ import annotations

import ast
import re
from typing import Optional

from skills.security_scanner.patterns import Pattern, PATTERN_MAP


def _is_static_arg(node: ast.AST) -> bool:
    """Check if an AST node is a static/literal argument (not from a variable).

    ``ast.Constant`` covers all literals on Python 3.8+; the legacy ``ast.Str``/
    ``Num``/``Bytes`` aliases were removed in 3.12, so we no longer reference them.
    """
    return isinstance(node, ast.Constant)


def _get_call_name(node: ast.Call) -> Optional[str]:
    """Extract the fully qualified name of a call target."""
    if isinstance(node.func, ast.Name):
        return node.func.id
    elif isinstance(node.func, ast.Attribute):
        parts = []
        current = node.func
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return ".".join(reversed(parts))
    return None


def _has_user_input_context(node: ast.AST) -> bool:
    """Check if a node is in a context likely involving user input."""
    # Check for f-strings, format(), or variable interpolation
    parents = []
    # Walk up the tree isn't easily done with ast.NodeVisitor alone.
    # We check by looking for specific patterns in the args.
    if isinstance(node, ast.Call):
        for arg in node.args:
            # f-string or Call (variable)
            if isinstance(arg, ast.JoinedStr):  # f-string
                return True
            if isinstance(arg, ast.Name) and arg.id not in ("__file__", "__name__", "sys"):
                return True
        for kw in node.keywords:
            if isinstance(kw.value, ast.Name) and kw.value.id not in ("__file__", "__name__", "sys"):
                return True
    return False


class SecurityASTChecker(ast.NodeVisitor):
    """AST visitor that detects security issues."""

    def __init__(self, source: str, filepath: str):
        self.source = source
        self.filepath = filepath
        self.findings: list[dict] = []

    def visit_Call(self, node: ast.Call):
        """Detect dangerous function calls."""
        name = _get_call_name(node)
        if not name:
            self.generic_visit(node)
            return

        # ── eval/exec checks ──
        if name in ("eval", "exec", "compile"):
            is_static = all(_is_static_arg(arg) for arg in node.args)
            if is_static:
                self._add_finding("eval_call" if name == "eval" else "exec_call",
                                  node, "static argument (verify it's intentional)")
            else:
                self._add_finding("eval_call" if name == "eval" else "exec_call",
                                  node, "dynamic argument — code injection risk")

        # ── __import__ ──
        elif name == "__import__":
            if any(_has_user_input_context(arg) for arg in node.args):
                self._add_finding("import_call", node,
                                  "import from dynamic source")
            elif not all(_is_static_arg(arg) for arg in node.args):
                self._add_finding("import_call", node,
                                  "dynamic import without whitelist")

        # ── subprocess shell=True ──
        elif "subprocess" in name and ("run" in name or "call" in name or "Popen" in name):
            for kw in node.keywords:
                if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                    if _has_user_input_context(node):
                        self._add_finding("subprocess_shell", node,
                                          "shell=True with dynamic input")
                    else:
                        self._add_finding("subprocess_shell", node,
                                          "shell=True (verify no user input)")

        # ── os.system / os.popen ──
        elif name == "os.system":
            if len(node.args) > 0 and _has_user_input_context(node):
                self._add_finding("os_system", node,
                                  "command from variable/input")
            else:
                self._add_finding("os_system", node,
                                  "os.system call (verify static)")
        elif name == "os.popen":
            self._add_finding("os_popen", node, "os.popen call")

        # ── shutil.rmtree ──
        elif name == "shutil.rmtree":
            self._add_finding("shutil_rmtree", node,
                              "recursive delete")

        # ── tempfile ──
        elif name in ("tempfile.mktemp", "tempfile.TemporaryFile", "tempfile.NamedTemporaryFile"):
            self._add_finding("tempfile_unsafe", node,
                              "tempfile (verify security)")

        # ── open write to sensitive paths ──
        elif name == "open" or (isinstance(node.func, ast.Name) and node.func.id == "open"):
            if len(node.args) >= 2:
                mode_arg = node.args[1]
                if isinstance(mode_arg, ast.Constant) and "w" in str(mode_arg.value):
                    path_arg = node.args[0]
                    if isinstance(path_arg, ast.Constant) and isinstance(path_arg.value, str):
                        if path_arg.value.startswith(("/etc", "/boot", "/dev", "/proc", "/sys", "/root")):
                            self._add_finding("open_write_critical", node,
                                              f"write to system path: {path_arg.value}")
                        elif ".." in path_arg.value:
                            self._add_finding("open_write_relative", node,
                                              f"relative path with ..: {path_arg.value}")

        # ── os.environ usage ──
        elif "os.environ" in name or (isinstance(node.func, ast.Attribute)
                                      and isinstance(node.func.value, ast.Attribute)
                                      and hasattr(node.func.value, "attr")
                                      and node.func.value.attr == "environ"):
            pass  # patterns.py handles this via regex

        self.generic_visit(node)

    def _add_finding(self, pattern_name: str, node: ast.AST, detail: str = ""):
        """Add a finding from AST analysis."""
        pattern = PATTERN_MAP.get(pattern_name)
        if not pattern:
            return
        self.findings.append({
            "file": self.filepath,
            "line": getattr(node, "lineno", 0),
            "col": getattr(node, "col_offset", 0),
            "pattern": pattern_name,
            "severity": pattern.severity.value,
            "detail": detail,
            "source": "ast",
        })


def analyze_ast(source: str, filepath: str) -> list[dict]:
    """Run AST analysis on Python source.

    Returns list of findings (empty if parsing fails).
    """
    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return [{
            "file": filepath,
            "line": 0,
            "col": 0,
            "pattern": "parse_error",
            "severity": "warning",
            "detail": "File could not be parsed as Python",
            "source": "ast",
        }]
    checker = SecurityASTChecker(source, filepath)
    checker.visit(tree)
    return checker.findings
