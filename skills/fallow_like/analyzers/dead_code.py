"""Dead code detection using AST analysis."""

from __future__ import annotations
from skills.fallow_like.scanner import ScanResult, Symbol
from skills.fallow_like.models import DeadCodeFinding, Severity
from collections import defaultdict


class DeadCodeAnalyzer:
    def __init__(self, min_confidence: float = 0.8):
        self.min_confidence = min_confidence

# DEAD CODE (Porthos):     def analyze(self, scan: ScanResult) -> list:
        findings = []
        definitions: dict[str, list[tuple[str, Symbol]]] = defaultdict(list)
        usages: dict[str, int] = defaultdict(int)

        for file_ast in scan.files:
            for sym in file_ast.symbols:
                if sym.type in ("function", "class", "variable"):
                    definitions[sym.name].append((file_ast.path, sym))

            for imp in file_ast.imports:
                parts = imp.replace("import ", "").replace("from ", "").split()
                for p in parts:
                    p = p.strip().strip(",").strip(";")
                    if p and p not in ("*", "as"):
                        usages[p] += 1

            for exp in file_ast.exports:
                usages[exp] += 1

        for name, locations in definitions.items():
            usage_count = usages.get(name, 0)
            if name in ("main", "__init__", "setup", "create_app", "index"):
                continue
            for fpath, sym in locations:
                if "test" in fpath.lower() or "spec" in fpath.lower():
                    usage_count += 1

            if usage_count == 0:
                for fpath, sym in locations:
                    findings.append(DeadCodeFinding(
                        rule_id="DEAD001",
                        severity=Severity.WARNING,
                        message=f"Unused {sym.type} '{name}'",
                        file=fpath,
                        line=sym.line,
                        column=sym.column,
                        end_line=sym.end_line,
                        symbol_type=sym.type,
                        symbol_name=name,
                        references_found=0,
                        confidence=0.9 if sym.type == "function" else 0.7,
                        fix_hint=f"Remove unused {sym.type} '{name}' or export it",
                    ))

        return findings