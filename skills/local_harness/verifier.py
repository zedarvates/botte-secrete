"""Verifier — deterministic, 0-token checks that catch a local model's hallucinations.

Layer 3 of the local-model harness (docs/plans/2026-06-26_local-model-harness-spec.md).
After a constrained model returns (ideally JSON), these decide whether to trust the
answer or escalate. Pure stdlib — no LLM call:

    schema_ok            output matches the declared shape (types/required/enum/range)
    evidence_in_context  every cited evidence span actually appears in the source text
    citations_exist      every cited file / file:symbol exists on disk
    code_parses          generated code at least parses

A claim the model cannot ground is a hallucination → the check fails → the harness
escalates instead of returning fiction.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass
class CheckResult:
    ok: bool
    detail: str = ""


@dataclass
class VerifyResult:
    ok: bool
    checks: dict  # name -> CheckResult

    def to_dict(self) -> dict:
        return {"ok": self.ok,
                "checks": {k: {"ok": v.ok, "detail": v.detail} for k, v in self.checks.items()}}


# ── individual checks ──────────────────────────────────────────────────────────

_JSON_TYPES = {"string": str, "number": (int, float), "integer": int,
               "boolean": bool, "array": list, "object": dict}


def schema_ok(obj: Any, schema: dict) -> CheckResult:
    """Validate a dict against a minimal JSON-schema subset (stdlib, no deps)."""
    if not isinstance(obj, dict):
        return CheckResult(False, "output is not a JSON object")
    errors: list[str] = []
    for key in schema.get("required", []):
        if key not in obj:
            errors.append(f"missing required '{key}'")
    for key, spec in schema.get("properties", {}).items():
        if key not in obj:
            continue
        val = obj[key]
        t = spec.get("type")
        if t in _JSON_TYPES and not isinstance(val, _JSON_TYPES[t]):
            errors.append(f"'{key}' should be {t}")
            continue
        if "enum" in spec and val not in spec["enum"]:
            errors.append(f"'{key}'={val!r} not in enum")
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            if "minimum" in spec and val < spec["minimum"]:
                errors.append(f"'{key}' below minimum")
            if "maximum" in spec and val > spec["maximum"]:
                errors.append(f"'{key}' above maximum")
    return CheckResult(not errors, "; ".join(errors) or "schema ok")


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s).lower()).strip()


def evidence_in_context(evidence: Any, context: str) -> CheckResult:
    """Every evidence span must appear (normalized) in the provided context.

    This is the anti-fabrication check: a model 'quoting' something not in its
    source is hallucinating."""
    spans = [evidence] if isinstance(evidence, str) else list(evidence or [])
    ctx = _norm(context)
    missing = [e for e in spans if _norm(e) and _norm(e) not in ctx]
    if missing:
        return CheckResult(False, f"{len(missing)} span(s) not in context: {missing[:3]}")
    return CheckResult(True, f"{len(spans)} span(s) grounded")


_DEF_RE = "|".join(["def", "class", "fn", "func", "function", "type", "interface", "struct"])


def citations_exist(citations: Any, repo_root: str) -> CheckResult:
    """Every cited file (or file:symbol / file:lineno) must exist on disk."""
    cits = [citations] if isinstance(citations, str) else list(citations or [])
    root = Path(repo_root)
    missing: list[str] = []
    for c in cits:
        path_part, _, symbol = str(c).partition(":")
        p = root / path_part
        if not p.exists():
            missing.append(c)
            continue
        if symbol and not symbol.isdigit():  # file:symbol → symbol must be defined
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                missing.append(c)
                continue
            if not re.search(rf"\b(?:{_DEF_RE})\s+{re.escape(symbol)}\b", text):
                missing.append(c)
    if missing:
        return CheckResult(False, f"{len(missing)} citation(s) not found: {missing[:3]}")
    return CheckResult(True, f"{len(cits)} citation(s) exist")


def code_parses(code: str, lang: str = "python") -> CheckResult:
    """Generated code must at least parse. Python via ast; others via bracket balance."""
    if not code or not str(code).strip():
        return CheckResult(False, "empty code")
    if lang == "python":
        try:
            ast.parse(code)
            return CheckResult(True, "python parses")
        except SyntaxError as e:
            return CheckResult(False, f"SyntaxError: {e.msg} (line {e.lineno})")
    pairs, opens, depth = {")": "(", "]": "[", "}": "{"}, set("([{"), 0
    for ch in code:
        if ch in opens:
            depth += 1
        elif ch in pairs:
            depth -= 1
            if depth < 0:
                return CheckResult(False, "unbalanced brackets")
    return CheckResult(depth == 0, "balanced" if depth == 0 else "unbalanced brackets")


# ── orchestrator ────────────────────────────────────────────────────────────────

def verify(output: Any, checks: list[str], *, context: Optional[str] = None,
           repo_root: Optional[str] = None, schema: Optional[dict] = None,
           code_field: str = "code", evidence_field: str = "evidence",
           citations_field: str = "citations") -> VerifyResult:
    """Run the requested checks on a model `output`; ok iff all pass.

    `output` is usually the dict from LocalLLMClient.chat_json. Checks pull their
    inputs from named fields (evidence/citations/code) so one spec drives them all.
    """
    def _field(name: str, default):
        return output.get(name, default) if isinstance(output, dict) else default

    results: dict[str, CheckResult] = {}
    for name in checks:
        if name == "schema":
            results[name] = schema_ok(output, schema or {})
        elif name == "evidence_in_context":
            results[name] = evidence_in_context(_field(evidence_field, []), context or "")
        elif name == "citations_exist":
            results[name] = citations_exist(_field(citations_field, []), repo_root or ".")
        elif name == "code_parses":
            results[name] = code_parses(_field(code_field, output if isinstance(output, str) else ""))
        else:
            results[name] = CheckResult(False, f"unknown check '{name}'")
    return VerifyResult(ok=all(r.ok for r in results.values()), checks=results)
