"""Regression tests for the deterministic committed-rule audit."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from skills.directives_audit.rules import (
    RULES_SCHEMA,
    audit_rules,
    rule_semantic_sha256,
)


def _ok(label: str, condition: bool, state: list[int]) -> None:
    print(f"  [{'PASS' if condition else 'FAIL'}] {label}")
    state[0 if condition else 1] += 1


def _rule(rule_id: str = "authority.test", *, effect: str = "DENY") -> dict:
    item = {
        "id": rule_id,
        "action": "unsafe-transition",
        "effect": effect,
        "scope": ["mission-worker"],
        "statement": "Policy rule: unsafe transitions remain blocked.",
        "source_ref": "policy.md#Policy rule",
        "owner_only": True,
        "enforced": True,
        "enforcement_refs": ["guard.py#def guard"],
        "probes": [
            {
                "id": f"{rule_id}.allow",
                "polarity": "allow",
                "evidence_ref": "test_guard.py#test_safe_action_allowed",
            },
            {
                "id": f"{rule_id}.deny",
                "polarity": "deny",
                "evidence_ref": "test_guard.py#test_unsafe_action_blocked",
            },
        ],
        "supersedes": [],
        "last_verified": {
            "at": "2026-09-01T00:00:00+00:00",
            "content_sha256": "0" * 64,
            "evidence_ref": "test_guard.py#test_unsafe_action_blocked",
        },
    }
    item["last_verified"]["content_sha256"] = rule_semantic_sha256(item)
    return item


def _write_project(root: Path, rules: list[dict]) -> None:
    (root / ".botte").mkdir(exist_ok=True)
    (root / "policy.md").write_text(
        "Policy rule: unsafe transitions remain blocked.\n"
        "Replacement rule: safe transitions are allowed.\n",
        encoding="utf-8",
    )
    (root / "guard.py").write_text("def guard():\n    return False\n", encoding="utf-8")
    (root / "test_guard.py").write_text(
        "def test_safe_action_allowed():\n    assert True\n\n"
        "def test_unsafe_action_blocked():\n    assert True\n",
        encoding="utf-8",
    )
    (root / ".botte" / "rules.json").write_text(
        json.dumps({"schema": RULES_SCHEMA, "rules": rules}, indent=2),
        encoding="utf-8",
    )


def _codes(report: dict) -> set[str]:
    return {item["code"] for item in report["findings"]}


def main() -> int:
    state = [0, 0]
    print("== rules drift tests ==")

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        missing = audit_rules(root)
        _ok("missing optional manifest is explicit and non-fabricated",
            not missing["manifest_present"] and missing["summary"]["rules"] == 0,
            state)

        canonical = _rule()
        _write_project(root, [canonical])
        clean = audit_rules(root)
        clean_again = audit_rules(root)
        _ok("valid source, guard and bidirectional probes audit cleanly",
            clean["manifest_present"] and clean["summary"] == {
                "rules": 1,
                "errors": 0,
                "warnings": 0,
                "conflicts": 0,
                "unenforced": 0,
                "stale": 0,
            }, state)
        _ok("audit fingerprint is deterministic and privacy-safe",
            clean["fingerprint"] == clean_again["fingerprint"]
            and str(root) not in json.dumps(clean), state)

        (root / "policy.md").write_text(
            "Policy rule: wording changed after review.\n", encoding="utf-8"
        )
        drifted = audit_rules(root)
        _ok("exact policy statement drift is detected",
            "semantic_statement_drift" in _codes(drifted), state)

        _write_project(root, [canonical])
        missing_probe = _rule()
        missing_probe["probes"] = missing_probe["probes"][:1]
        missing_probe["last_verified"]["content_sha256"] = rule_semantic_sha256(missing_probe)
        _write_project(root, [missing_probe])
        no_deny = audit_rules(root)
        _ok("enforced rules require allow and deny probes",
            "unenforced_missing_probe" in _codes(no_deny), state)

        broken_guard = _rule()
        broken_guard["enforcement_refs"] = ["guard.py#missing guard anchor"]
        broken_guard["last_verified"]["content_sha256"] = rule_semantic_sha256(broken_guard)
        _write_project(root, [broken_guard])
        no_guard = audit_rules(root)
        _ok("missing guard anchors fail closed",
            "enforcement_anchor_missing" in _codes(no_guard), state)

        first = _rule("authority.original", effect="DENY")
        second = _rule("authority.replacement", effect="ALLOW")
        second["statement"] = "Replacement rule: safe transitions are allowed."
        second["source_ref"] = "policy.md#Replacement rule"
        second["last_verified"]["content_sha256"] = rule_semantic_sha256(second)
        _write_project(root, [first, second])
        conflict = audit_rules(root)
        _ok("contradictory active effects on overlapping scope are rejected",
            conflict["summary"]["conflicts"] == 1
            and "rule_conflict" in _codes(conflict), state)

        first["supersedes"] = ["authority.replacement"]
        first["last_verified"]["content_sha256"] = rule_semantic_sha256(first)
        second["supersedes"] = ["authority.original"]
        second["last_verified"]["content_sha256"] = rule_semantic_sha256(second)
        _write_project(root, [first, second])
        cycle = audit_rules(root)
        _ok("cyclic supersession cannot hide a contradiction",
            "supersedes_cycle" in _codes(cycle), state)

        stale = _rule()
        stale["scope"] = ["changed-after-verification"]
        _write_project(root, [stale])
        stale_report = audit_rules(root)
        _ok("semantic receipt detects unreviewed rule edits",
            stale_report["summary"]["stale"] == 1
            and "verification_stale" in _codes(stale_report), state)

        escaping = _rule()
        escaping["source_ref"] = "../policy.md#Policy rule"
        escaping["last_verified"]["content_sha256"] = rule_semantic_sha256(escaping)
        _write_project(root, [escaping])
        escaped = audit_rules(root)
        _ok("references cannot escape the project root",
            "source_ref_invalid" in _codes(escaped), state)

    print(f"\nRESULT: {state[0]} passed, {state[1]} failed")
    return 0 if state[1] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
