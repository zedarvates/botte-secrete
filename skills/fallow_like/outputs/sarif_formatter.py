"""SARIF output formatter (CodeQL compatible)."""

from __future__ import annotations
import json
from skills.fallow_like.models import AnalysisResult, Finding, Severity

SARIF_VERSION = "2.1.0"
SARIF_SCHEMA = "https://schemastore.azurewebsites.net/schemas/json/sarif-2.1.0-rtm.5.json"

SEVERITY_MAP = {
    "info": "note",
    "warning": "warning",
    "error": "error",
    "critical": "error",
}


def format(result: AnalysisResult) -> str:
    rules: dict = {}
    results: list = []

    all_findings: list[Finding] = (
        list(result.dead_code) + list(result.duplication) +
        list(result.complexity) + list(result.boundaries) +
        list(result.feature_flags) + list(result.hot_paths) +
        list(result.blast_radius) + list(result.secrets)
    )

    for f in all_findings:
        if f.rule_id not in rules:
            rules[f.rule_id] = {
                "id": f.rule_id,
                "shortDescription": {"text": f.message[:100]},
                "defaultConfiguration": {
                    "level": SEVERITY_MAP.get(f.severity.value, "note")
                },
            }
        results.append({
            "ruleId": f.rule_id,
            "level": SEVERITY_MAP.get(f.severity.value, "note"),
            "message": {"text": f.message},
            "locations": [{
                "physicalLocation": {
                    "artifactLocation": {"uri": f.file},
                    "region": {"startLine": f.line, "startColumn": f.column},
                },
            }],
        })

    sarif = {
        "$schema": SARIF_SCHEMA,
        "version": SARIF_VERSION,
        "runs": [{
            "tool": {
                "driver": {
                    "name": "fallow-like",
                    "version": "0.1.0",
                    "rules": list(rules.values()),
                },
            },
            "results": results,
        }],
    }

    return json.dumps(sarif, indent=2)
