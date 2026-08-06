"""Taint / data-flow security analysis — neuro-symbolic, local-first.

Inspired by RepoAudit's source→sink data-flow scan, in botte's local-first
shape:

  symbolic (0 tokens)   Python ``ast`` finds attacker-controlled *sources*
                        (argv, env, request, input) flowing into dangerous
                        *sinks* (subprocess/eval/exec, SQL, pickle/yaml, urlopen)
                        plus insecure-by-default calls. No compilation needed.
  neuro (0 cloud tokens, optional)
                        a LOCAL model judges each candidate (exploitable vs
                        sanitized) when ``judge=True`` and a backend is reachable;
                        it only ever annotates/adjusts confidence, never invents.

v1 does precise intra-procedural data flow for **Python** (botte's primary
language and self-audit target). Other languages are scanned for symbols but not
yet taint-tracked — that's the next iteration.
"""

from __future__ import annotations

import ast

from skills.fallow_like.models import Severity, TaintFinding

# ── source catalogue (attacker-controlled value producers) ───────────────────
SOURCE_CALLS = {"input", "os.getenv", "os.environ.get", "getpass.getpass"}
SOURCE_SUBSCRIPT_ROOTS = {"sys.argv", "os.environ"}
# Frameworks expose request-bound data off a global/handle named like this.
SOURCE_ATTR_ROOTS = {"request", "flask_request"}

# ── sink catalogue → (CWE, label, severity) ──────────────────────────────────
SINKS = {
    "os.system":        ("CWE-78", "OS command injection", Severity.CRITICAL),
    "os.popen":         ("CWE-78", "OS command injection", Severity.CRITICAL),
    "subprocess.run":   ("CWE-78", "OS command injection", Severity.ERROR),
    "subprocess.call":  ("CWE-78", "OS command injection", Severity.ERROR),
    "subprocess.Popen": ("CWE-78", "OS command injection", Severity.ERROR),
    "subprocess.check_output": ("CWE-78", "OS command injection", Severity.ERROR),
    "eval":             ("CWE-94", "Code injection (eval)", Severity.CRITICAL),
    "exec":             ("CWE-94", "Code injection (exec)", Severity.CRITICAL),
    "pickle.load":      ("CWE-502", "Insecure deserialization", Severity.ERROR),
    "pickle.loads":     ("CWE-502", "Insecure deserialization", Severity.ERROR),
    "marshal.loads":    ("CWE-502", "Insecure deserialization", Severity.ERROR),
    "yaml.load":        ("CWE-502", "Unsafe YAML load (use safe_load)", Severity.ERROR),
    "urllib.request.urlopen": ("CWE-918", "Server-side request forgery", Severity.WARNING),
    "requests.get":     ("CWE-918", "Server-side request forgery", Severity.WARNING),
    "requests.post":    ("CWE-918", "Server-side request forgery", Severity.WARNING),
}
SQL_SINK_METHODS = {"execute", "executemany", "executescript"}


# ── ast helpers ──────────────────────────────────────────────────────────────

def _dotted(node) -> str:
    """ast attribute/name chain → dotted string (os.path.join)."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _root_name(node) -> str:
    """Leftmost Name id of an attribute/subscript/call chain."""
    while True:
        if isinstance(node, ast.Attribute):
            node = node.value
        elif isinstance(node, ast.Subscript):
            node = node.value
        elif isinstance(node, ast.Call):
            node = node.func
        elif isinstance(node, ast.Name):
            return node.id
        else:
            return ""


def _is_source_expr(node) -> bool:
    """True if this single node directly produces attacker-controlled data."""
    if isinstance(node, ast.Call):
        if _dotted(node.func) in SOURCE_CALLS:
            return True
        if _root_name(node.func) in SOURCE_ATTR_ROOTS:
            return True
    if isinstance(node, ast.Subscript) and _dotted(node.value) in SOURCE_SUBSCRIPT_ROOTS:
        return True
    if isinstance(node, ast.Attribute) and _root_name(node) in SOURCE_ATTR_ROOTS:
        return True
    if isinstance(node, ast.Name) and node.id in SOURCE_ATTR_ROOTS:
        return True
    return False


def _expr_tainted(node, tainted: set) -> bool:
    """True if the expression depends on a source or an already-tainted name."""
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and n.id in tainted:
            return True
        if _is_source_expr(n):
            return True
    return False


def _target_names(target) -> list:
    names = []
    for n in ast.walk(target):
        if isinstance(n, ast.Name):
            names.append(n.id)
    return names


def _scope_nodes(scope):
    """Yield nodes of this scope, NOT descending into nested function defs.

    Keeps module scope and each function scope separate so a sink isn't reported
    twice and taint doesn't leak across function boundaries (intra-procedural).
    """
    stack = list(getattr(scope, "body", []))
    while stack:
        n = stack.pop()
        yield n
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue  # nested function — its own scope is scanned separately
        stack.extend(ast.iter_child_nodes(n))


def _is_dynamic_string(node) -> bool:
    """A SQL string built at runtime (f-string, %-format, +concat, .format)."""
    if isinstance(node, ast.JoinedStr):  # f-string with actual interpolation
        return any(isinstance(value, ast.FormattedValue) for value in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod)):
        return True
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
            and node.func.attr == "format":
        return True
    return False


def _source_label(node, tainted: set) -> str:
    """Best-effort name of the source feeding a tainted expression."""
    for n in ast.walk(node):
        if _is_source_expr(n):
            if isinstance(n, ast.Call):
                return _dotted(n.func) or _root_name(n.func)
            if isinstance(n, ast.Subscript):
                return _dotted(n.value)
            if isinstance(n, ast.Attribute):
                return _dotted(n)
            if isinstance(n, ast.Name):
                return n.id
        if isinstance(n, ast.Name) and n.id in tainted:
            return n.id
    return "tainted input"


class TaintAnalyzer:
    """Find source→sink data flows + insecure-by-default calls in Python."""

    def __init__(self, judge: bool = False):
        self.judge = judge

    def analyze(self, scan) -> list:
        findings: list = []
        for file_ast in scan.files:
            if file_ast.language != "python":
                continue
            try:
                tree = ast.parse(file_ast.source.decode("utf-8", "replace"))
            except SyntaxError:
                continue
            self._scan_scope(tree, "<module>", file_ast.path, findings)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self._scan_scope(node, node.name, file_ast.path, findings)

        if self.judge and findings:
            self._judge(findings, scan)
        return findings

    def _scan_scope(self, scope, fn_name: str, path: str, findings: list) -> None:
        """Compute tainted names in a scope, then flag tainted/insecure sinks."""
        nodes = list(_scope_nodes(scope))
        tainted: set = set()
        # Two forward passes catch values used before their tainting assignment.
        for _ in range(2):
            for node in nodes:
                if isinstance(node, ast.Assign) and _expr_tainted(node.value, tainted):
                    for tgt in node.targets:
                        tainted.update(_target_names(tgt))
                elif isinstance(node, (ast.AugAssign, ast.AnnAssign)) \
                        and node.value is not None and _expr_tainted(node.value, tainted):
                    tainted.update(_target_names(node.target))

        for node in nodes:
            if isinstance(node, ast.Call):
                self._check_call(node, tainted, fn_name, path, findings)

    def _check_call(self, call, tainted, fn_name, path, findings) -> None:
        dotted = _dotted(call.func)
        # 1. catalogued dangerous sinks
        if dotted in SINKS:
            cwe, label, sev = SINKS[dotted]
            insecure = self._insecure_default(dotted, call)
            # Only the sink payload is security-sensitive. Treating cwd, env,
            # timeout, or stdin as the command/URL produced false positives.
            payloads = list(call.args[:1])
            if not payloads:
                keyword = "args" if dotted.startswith("subprocess.") else "url"
                payloads = [kw.value for kw in call.keywords if kw.arg == keyword]
            tainted_arg = next(
                (arg for arg in payloads if _expr_tainted(arg, tainted)), None
            )
            if insecure:
                self._add(findings, path, call, fn_name, cwe,
                          f"{label} — insecure by default", dotted,
                          "insecure default", sev, 0.75)
            elif tainted_arg is not None:
                self._add(findings, path, call, fn_name, cwe,
                          f"{label} — attacker-controlled input reaches {dotted}()",
                          dotted, _source_label(tainted_arg, tainted), sev, 0.7)
            return

        # 2. SQL execute(...) with a tainted or runtime-built query string
        if isinstance(call.func, ast.Attribute) and call.func.attr in SQL_SINK_METHODS \
                and call.args:
            q = call.args[0]
            if _expr_tainted(q, tainted):
                self._add(findings, path, call, fn_name, "CWE-89",
                          "SQL injection — tainted value in query string",
                          f".{call.func.attr}()", _source_label(q, tainted),
                          Severity.ERROR, 0.8)
            elif _is_dynamic_string(q):
                self._add(findings, path, call, fn_name, "CWE-89",
                          "SQL injection risk — query built by string formatting "
                          "(use parameterised queries)",
                          f".{call.func.attr}()", "dynamic string",
                          Severity.WARNING, 0.6)

    @staticmethod
    def _insecure_default(dotted: str, call) -> bool:
        kw = {k.arg: k.value for k in call.keywords}
        if dotted.startswith("subprocess.") or dotted == "os.system":
            shell = kw.get("shell")
            shell_true = isinstance(shell, ast.Constant) and shell.value is True
            dyn = bool(call.args) and not isinstance(call.args[0], ast.Constant)
            return shell_true and dyn
        if dotted == "yaml.load":
            # safe only when an explicit safe Loader is passed
            loader = kw.get("Loader")
            return not (loader is not None and "Safe" in _dotted(loader))
        return False

    @staticmethod
    def _add(findings, path, call, fn_name, cwe, message, sink, source, sev, conf):
        findings.append(TaintFinding(
            rule_id="TAINT001",
            severity=sev,
            message=message,
            file=path,
            line=call.lineno,
            column=call.col_offset,
            end_line=getattr(call, "end_lineno", call.lineno),
            confidence=conf,
            tags=[cwe, "security", "data-flow"],
            cwe=cwe, source=source, sink=sink, function=fn_name,
            fix_hint=f"Validate/sanitise '{source}' or avoid {sink}; see {cwe}.",
        ))

    # ── neuro layer (optional, local-only, 0 cloud tokens) ───────────────────
    def _judge(self, findings, scan) -> None:
        """Ask a LOCAL model to confirm each candidate. Best-effort, guarded."""
        try:
            from skills.llm_backends.client import LocalLLMClient, LocalLLMError
            from skills.llm_backends import registry
        except ImportError:
            return
        if not registry.best_chat_backend():
            return
        src_by_path = {f.path: f.source for f in scan.files}
        client = LocalLLMClient()
        for fnd in findings:
            snippet = self._snippet(src_by_path.get(fnd.file, b""), fnd.line)
            prompt = (
                f"Security candidate ({fnd.cwe}): {fnd.message}\n"
                f"Code around line {fnd.line}:\n{snippet}\n\n"
                "Is this actually exploitable, or is the input validated/constant? "
                'Reply STRICT JSON: {"verdict":"exploitable|sanitized|unknown",'
                '"confidence":0.0-1.0}.')
            try:
                out = client.chat(prompt, max_tokens=120, temperature=0.0).text
            except LocalLLMError:
                continue
            import json
            import re as _re
            m = _re.search(r"\{.*\}", out, _re.S)
            if not m:
                continue
            try:
                d = json.loads(m.group(0))
            except json.JSONDecodeError:
                continue
            fnd.verdict = str(d.get("verdict", "")).lower()[:20]
            if fnd.verdict == "sanitized":
                fnd.confidence = round(fnd.confidence * 0.4, 2)
            elif fnd.verdict == "exploitable":
                fnd.confidence = min(0.95, round(fnd.confidence + 0.2, 2))

    @staticmethod
    def _snippet(source: bytes, line: int, ctx: int = 3) -> str:
        try:
            lines = source.decode("utf-8", "replace").splitlines()
        except Exception:
            return ""
        lo, hi = max(0, line - ctx - 1), min(len(lines), line + ctx)
        return "\n".join(lines[lo:hi])
