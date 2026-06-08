"""Static feature flag detection."""

from __future__ import annotations
from skills.fallow_like.scanner import ScanResult
from skills.fallow_like.models import FeatureFlagFinding, Severity
import re


class FeatureFlagAnalyzer:
    FLAG_PATTERNS = [
        (r'feature_flag["\s:=]+\s*["\']([\w_]+)', "toggle"),
        (r'featureToggle["\s:=]+\s*["\']([\w_]+)', "toggle"),
        (r'isFeatureEnabled["\(]+\s*["\']([\w_]+)', "toggle"),
        (r'if\s*\(\s*FLAGS\[?\s*["\']([\w_]+)', "toggle"),
        (r'flags\.(get|check|isEnabled)\s*\(?\s*["\']([\w_]+)', "toggle"),
        (r'experiments?\.(get|is|check)\s*\(?\s*["\']([\w_]+)', "experiment"),
        (r'ab_test\s*\(?\s*["\']([\w_]+)', "experiment"),
        (r'permission[s]?\.check\s*\(?\s*["\']([\w_]+)', "permission"),
        (r'hasPermission\s*\(?\s*["\']([\w_]+)', "permission"),
        (r'@deprecated', "deprecated"),
        (r'DEPRECATED_\w+', "deprecated"),
    ]

    def analyze(self, scan: ScanResult) -> list:
        findings = []
        flag_locations: dict[str, list[str]] = {}

        for file_ast in scan.files:
            try:
                text = file_ast.source.decode("utf-8", errors="replace")
            except Exception:
                continue

            for pattern, flag_type in self.FLAG_PATTERNS:
                for match in re.finditer(pattern, text, re.IGNORECASE):
                    flag_name = match.group(1) if match.lastindex else match.group(0)
                    line_num = text[:match.start()].count("\n") + 1
                    loc = f"{file_ast.path}:{line_num}"

                    if flag_name not in flag_locations:
                        flag_locations[flag_name] = []
                    flag_locations[flag_name].append(loc)

        for flag_name, locations in flag_locations.items():
            flag_type = self._classify_flag(flag_name)
            stale = self._is_stale(flag_name, locations)
            findings.append(FeatureFlagFinding(
                rule_id="FLAG001",
                severity=Severity.WARNING if stale else Severity.INFO,
                message=f"Feature flag '{flag_name}' ({flag_type}) in {len(locations)} location(s)",
                file=locations[0].split(":")[0],
                line=int(locations[0].split(":")[1]) if ":" in locations[0] else 0,
                flag_name=flag_name,
                flag_type=flag_type,
                locations=locations,
                stale=stale,
                confidence=0.8,
                fix_hint="Remove stale feature flags or document active ones",
            ))

        return findings

    def _classify_flag(self, name: str) -> str:
        n = name.lower()
        if "experiment" in n or "ab_" in n:
            return "experiment"
        if "permission" in n or "can_" in n or "has_" in n:
            return "permission"
        if "deprecated" in n or "old_" in n or "legacy" in n:
            return "deprecated"
        return "toggle"

    def _is_stale(self, name: str, locations: list[str]) -> bool:
        n = name.lower()
        if any(w in n for w in ["old", "legacy", "deprecated", "temp", "tmp", "test"]):
            return True
        if len(locations) <= 1:
            return True
        return False
