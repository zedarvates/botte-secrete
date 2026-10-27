#!/usr/bin/env python3
"""Focused tests for Asset Quality Memory."""

from __future__ import annotations

import tempfile

from skills.asset_quality import evaluate_asset, quality_status, record_verified


def _report(seed: int = 8, *, family: str = "mesh") -> dict:
    features = {
        "mesh": {"manifold": .9, "normals": .9, "prompt_alignment": seed / 10,
                 "scale": .8, "topology": .85, "uv": .8},
        "image": {"aesthetic": .8, "artifact_free": .9, "composition": .8,
                  "prompt_alignment": seed / 10, "technical": .9},
    }[family]
    checks = {"decodable": True, "license_verified": True, "manifest_verified": True}
    checks.update({"finite_geometry": True, "nonempty_geometry": True} if family == "mesh"
                  else {"dimensions_valid": True})
    return {"family": family, "sha256": f"{seed:064x}", "size_bytes": 1024 + seed,
            "checks": checks, "features": features}


def main() -> int:
    passed = failed = 0

    def check(label: str, condition: bool) -> None:
        nonlocal passed, failed
        print(f"  [{'PASS' if condition else 'FAIL'}] {label}")
        if condition:
            passed += 1
        else:
            failed += 1

    print("== asset quality tests ==")
    with tempfile.TemporaryDirectory() as project:
        incomplete = _report()
        del incomplete["checks"]["license_verified"]
        advice = evaluate_asset(incomplete, project_root=project)
        check("missing supply-chain proof abstains", advice.status == "incomplete")

        rejected = _report()
        rejected["checks"]["finite_geometry"] = False
        advice = evaluate_asset(rejected, project_root=project)
        check("hard geometry failure runs before k-NN",
              advice.status == "rule_fail" and advice.verdict == "FAIL")

        for seed in (7, 8):
            record_verified(_report(seed), project_root=project, verdict="pass",
                            verified_by="tests:mesh-harness", evidence_refs=(f"fixture:{seed}",))
        record_verified(_report(8), project_root=project, verdict="pass",
                        verified_by="tests:mesh-harness", evidence_refs=("fixture:duplicate",))
        duplicate_advice = evaluate_asset(_report(10), project_root=project)
        check("duplicate hashes cannot unlock k-NN support",
              duplicate_advice.status == "abstain" and duplicate_advice.neighbor_count == 2)
        record_verified(_report(9), project_root=project, verdict="pass",
                        verified_by="tests:mesh-harness", evidence_refs=("fixture:9",))
        suggestion = evaluate_asset(_report(10), project_root=project)
        check("three similar verified meshes unlock a shadow verdict",
              suggestion.status == "suggest" and suggestion.verdict == "PASS")
        check("neighbors are explainable and never act",
              len(suggestion.neighbors) == 3 and suggestion.shadow_only and not suggestion.acted)

        image = evaluate_asset(_report(8, family="image"), project_root=project)
        check("asset families have isolated indices",
              image.status == "abstain" and image.neighbor_count == 0)

        try:
            record_verified(_report(), project_root=project, verdict="pass",
                            verified_by="model:self-report")
            blocked = False
        except ValueError:
            blocked = True
        check("model self-report cannot label memory", blocked)

        status = quality_status(project)
        check("status exposes deduplicated readiness without activation",
              status["recorded_outcomes"] == 4 and status["verified_assets"] == 3
              and status["families_ready"] == ["mesh"] and status["activation_allowed"] is False)

    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
