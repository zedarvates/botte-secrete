"""Architecture boundary violation detection."""

from __future__ import annotations
from skills.fallow_like.scanner import ScanResult
from skills.fallow_like.models import BoundaryViolation, Severity
import re


class BoundaryAnalyzer:
    DEFAULT_LAYERS = {
        "presentation": [r"(ui|view|page|component|screen|widget)s?/"],
        "application": [r"(service|usecase|controller|handler|route)s?/"],
        "domain": [r"(model|domain|entity|value_object|aggregate)s?/"],
        "infrastructure": [r"(repo|repository|db|dao|adapter|client|infra)s?/"],
        "config": [r"(config|setting|env)s?/"],
    }

    ALLOWED_FLOWS = {
        "presentation": ["application", "domain", "config"],
        "application": ["domain", "infrastructure", "config"],
        "domain": ["config"],
        "infrastructure": ["domain", "config"],
        "config": [],
    }

    def analyze(self, scan: ScanResult) -> list:
        findings = []
        file_layers: dict[str, str] = {}

        for file_ast in scan.files:
            layer = self._detect_layer(file_ast.path)
            if layer:
                file_layers[file_ast.path] = layer

        for file_ast in scan.files:
            source_layer = file_layers.get(file_ast.path)
            if not source_layer:
                continue

            for imp in file_ast.imports:
                target_file = self._resolve_import(imp, file_ast.path, scan)
                if not target_file:
                    continue
                target_layer = file_layers.get(target_file)
                if not target_layer:
                    continue
                if target_layer not in self.ALLOWED_FLOWS.get(source_layer, []):
                    allowed = self.ALLOWED_FLOWS.get(source_layer, [])
                    fix = f"Move dependency to {allowed[0]} layer" if allowed else "Restructure"
                    findings.append(BoundaryViolation(
                        rule_id="BOUND001",
                        severity=Severity.ERROR,
                        message=(
                            f"Boundary violation: {source_layer} ({file_ast.path}) "
                            f"imports from {target_layer} ({target_file})"
                        ),
                        file=file_ast.path,
                        source_layer=source_layer,
                        target_layer=target_layer,
                        violation_type="import",
                        allowed=False,
                        fix_hint=fix,
                    ))

        return findings

    def _detect_layer(self, path: str) -> str | None:
        for layer, patterns in self.DEFAULT_LAYERS.items():
            for pattern in patterns:
                if re.search(pattern, path, re.IGNORECASE):
                    return layer
        return None

    def _resolve_import(self, import_stmt: str, source_file: str, scan: ScanResult) -> str | None:
        import_lower = import_stmt.lower()
        for file_ast in scan.files:
            if file_ast.path == source_file:
                continue
            stem = file_ast.path.split("/")[-1].split(".")[0].lower()
            if stem and stem in import_lower:
                return file_ast.path
        return None
