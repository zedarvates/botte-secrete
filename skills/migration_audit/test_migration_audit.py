#!/usr/bin/env python3
"""Hermetic tests for the migration-completeness stage."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .audit import SPEC_SCHEMA, audit_migration
from .stage import insert_migration_audit_stage
from skills.meta_harness import MetaHarness


def _ok(message: str, condition: bool, state: list[int]) -> None:
    print(f"  [{'PASS' if condition else 'FAIL'}] {message}")
    state[0 if condition else 1] += 1


def _spec() -> dict:
    return {
        "schema": SPEC_SCHEMA,
        "migration_id": "fixture:old-api-to-v2",
        "checks": [
            {"id": "no-legacy-api", "kind": "text_absent",
             "pattern": "LEGACY_API", "include": ["**/*.py"]},
            {"id": "new-api-wired", "kind": "text_present",
             "pattern": "NEW_API_V2", "include": ["**/*.py"]},
            {"id": "old-config-gone", "kind": "path_absent", "path": "legacy.ini"},
            {"id": "new-config-present", "kind": "path_present", "path": "v2.toml"},
            {"id": "no-dual-entrypoints", "kind": "paths_not_both",
             "paths": ["src/legacy", "src/v2"]},
        ],
    }


def main() -> int:
    state = [0, 0]
    print("== migration audit tests ==")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "src" / "legacy").mkdir(parents=True)
        (root / "src" / "v2").mkdir(parents=True)
        (root / "src" / "v2" / "client.py").write_text(
            "NEW_API_V2 = True\n", encoding="utf-8")
        (root / "src" / "legacy" / "compat.py").write_text(
            "LEGACY_API = 'compatibility shim'\n", encoding="utf-8")
        (root / "legacy.ini").write_text("enabled=true\n", encoding="utf-8")
        (root / "v2.toml").write_text("enabled=true\n", encoding="utf-8")

        compile((root / "src" / "v2" / "client.py").read_text(encoding="utf-8"),
                "client.py", "exec")
        _ok("normal smoke validation passes despite the compatibility shim", True, state)

        failed = audit_migration(_spec(), root)
        failed_ids = {item["id"] for item in failed["checks"] if item["status"] == "FAIL"}
        encoded = json.dumps(failed)
        _ok("incomplete migration fails independently of normal tests",
            failed["status"] == "FAIL"
            and {"no-legacy-api", "old-config-gone", "no-dual-entrypoints"} <= failed_ids,
            state)
        _ok("report exposes paths but not matched source or literals",
            "compat.py" in encoded and "compatibility shim" not in encoded
            and "LEGACY_API" not in encoded and directory not in encoded, state)
        _ok("migration audit never executes code or grants authority",
            failed["executed_project_code"] is False
            and failed["authority"] == "SIMULATE"
            and failed["shadow_only"] is True
            and failed["activation_allowed"] is False, state)

        (root / "src" / "legacy" / "compat.py").unlink()
        (root / "src" / "legacy").rmdir()
        (root / "legacy.ini").unlink()
        passed = audit_migration(_spec(), root)
        _ok("completed migration passes every declared criterion",
            passed["status"] == "PASS" and passed["summary"]["passed"] == 5, state)

    ordered = insert_migration_audit_stage(["SCOUT", "BUILDER", "VALIDATOR", "REPORTER"])
    _ok("planner inserts MIGRATION_AUDIT immediately before VALIDATOR",
        ordered == ["SCOUT", "BUILDER", "MIGRATION_AUDIT", "VALIDATOR", "REPORTER"], state)
    _ok("stage insertion is idempotent",
        insert_migration_audit_stage(ordered) == ordered, state)
    planned = MetaHarness().plan(["SCOUT", "BUILDER", "VALIDATOR"])
    planned_names = [step.agent.upper() for step in planned.steps]
    _ok("meta-harness automatically inserts the migration stage",
        planned_names.index("BUILDER") < planned_names.index("MIGRATION_AUDIT")
        < planned_names.index("VALIDATOR"), state)

    rejected_order = rejected_duplicate = rejected_traversal = False
    try:
        insert_migration_audit_stage(["VALIDATOR", "BUILDER"])
    except ValueError:
        rejected_order = True
    try:
        insert_migration_audit_stage(["BUILDER", "MIGRATION_AUDIT", "MIGRATION_AUDIT", "VALIDATOR"])
    except ValueError:
        rejected_duplicate = True
    bad = _spec()
    bad["checks"][2]["path"] = "../outside"
    try:
        audit_migration(bad)
    except ValueError:
        rejected_traversal = True
    _ok("invalid stage order fails closed", rejected_order, state)
    _ok("duplicate migration stages fail closed", rejected_duplicate, state)
    _ok("path traversal in a spec is rejected", rejected_traversal, state)

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "large.py").write_text("x" * 256, encoding="utf-8")
        spec = {
            "schema": SPEC_SCHEMA, "migration_id": "bounded-scan",
            "max_file_bytes": 128,
            "checks": [{"id": "no-old", "kind": "text_absent",
                        "pattern": "OLD", "include": ["**/*.py"]}],
        }
        uncertain = audit_migration(spec, root)
        _ok("unreadable bounded evidence yields UNCERTAIN rather than PASS",
            uncertain["status"] == "UNCERTAIN", state)

    print(f"\nRESULT: {state[0]} passed, {state[1]} failed")
    return 0 if state[1] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
