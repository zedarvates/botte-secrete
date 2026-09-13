"""Factory Assurance Layer.

The layer is intentionally deterministic. Models and agents may populate the
run record, but they do not decide whether evidence is sufficient for review.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REQUIRED_TOP_LEVEL = {
    "schema_version",
    "action_id",
    "stage",
    "mission",
    "actors",
    "effects",
    "evidence",
    "controls",
    "identity",
}

VALID_STAGES = {"observe", "consultative", "shadow", "gated", "bounded"}
VALID_EVIDENCE_STATUS = {"pass", "fail", "missing", "not_applicable"}


def load_run(path: str | Path) -> dict[str, Any]:
    """Load an assurance run record from JSON."""
    with Path(path).open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("assurance run must be a JSON object")
    return value


def _non_empty_strings(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(
        isinstance(item, str) and item.strip() for item in value
    )


def _add(blockers: list[str], condition: bool, message: str) -> None:
    if condition:
        blockers.append(message)


def evaluate_assurance(run: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a run record and return a stable, auditable decision.

    This function never returns an instruction to merge or deploy. A successful
    evaluation only means that the record is ready for independent human review.
    """
    blockers: list[str] = []
    warnings: list[str] = []

    missing = sorted(REQUIRED_TOP_LEVEL - set(run))
    _add(blockers, bool(missing), f"missing top-level fields: {', '.join(missing)}")
    if missing:
        return _result(run, blockers, warnings)

    _add(blockers, run.get("schema_version") != 1, "unsupported schema_version")
    stage = run.get("stage")
    _add(blockers, stage not in VALID_STAGES, f"unsupported stage: {stage!r}")

    mission = run.get("mission") or {}
    _add(blockers, not _non_empty_strings(mission.get("goals")), "mission.goals must be non-empty")
    _add(blockers, not _non_empty_strings(mission.get("invariants")), "mission.invariants must be non-empty")
    _add(
        blockers,
        not isinstance(mission.get("non_goals"), list),
        "mission.non_goals must be a list",
    )
    _add(
        blockers,
        not isinstance(mission.get("forbidden_transformations"), list),
        "mission.forbidden_transformations must be a list",
    )
    _add(
        blockers,
        mission.get("within_mission") is not True,
        "mission boundary is not positively established",
    )

    actors = run.get("actors") or {}
    builder = str(actors.get("builder") or "").strip()
    judge = str(actors.get("judge") or "").strip()
    _add(blockers, not builder, "builder identity is missing")
    _add(blockers, not judge, "independent judge identity is missing")
    _add(blockers, bool(builder and judge and builder == judge), "builder and judge must be independent")

    effects = run.get("effects") or {}
    declared = set(effects.get("declared") or [])
    observed = set(effects.get("observed") or [])
    unexpected = sorted(observed - declared)
    _add(blockers, bool(unexpected), "unexpected effects: " + ", ".join(unexpected))
    unresolved = effects.get("unresolved") or []
    _add(blockers, bool(unresolved), "unresolved effects remain")

    evidence = run.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        blockers.append("at least one evidence item is required")
    else:
        names: set[str] = set()
        for item in evidence:
            if not isinstance(item, dict):
                blockers.append("evidence items must be objects")
                continue
            name = str(item.get("name") or "").strip()
            status = item.get("status")
            required = item.get("required", True)
            if not name:
                blockers.append("evidence item has no name")
            elif name in names:
                blockers.append(f"duplicate evidence item: {name}")
            names.add(name)
            if status not in VALID_EVIDENCE_STATUS:
                blockers.append(f"evidence {name or '<unnamed>'} has invalid status")
            if required and status != "pass":
                blockers.append(f"required evidence did not pass: {name or '<unnamed>'}")

    controls = run.get("controls") or {}
    _add(
        blockers,
        controls.get("positive_control") != "pass",
        "positive control must pass",
    )
    _add(
        blockers,
        controls.get("negative_control") != "fail",
        "negative/mutation control must demonstrably fail",
    )
    _add(
        blockers,
        controls.get("holdout_scope") != "private_external",
        "holdout must be private/external to the builder-visible repository",
    )
    if not controls.get("historical_regressions_checked", False):
        warnings.append("historical regression corpus not checked")
    if not controls.get("adversarial_cases_checked", False):
        warnings.append("randomized/adversarial cases not checked")

    identity = run.get("identity") or {}
    source_sha = str(identity.get("source_sha") or "").strip()
    build_sha = str(identity.get("build_sha") or "").strip()
    tested_sha = str(identity.get("tested_sha") or "").strip()
    _add(blockers, not source_sha, "source_sha is missing")
    _add(blockers, not build_sha, "build_sha is missing")
    _add(blockers, not tested_sha, "tested_sha is missing")
    if source_sha and build_sha and tested_sha:
        _add(
            blockers,
            len({source_sha, build_sha, tested_sha}) != 1,
            "source/build/tested identity mismatch",
        )

    deployed_sha = str(identity.get("deployed_sha") or "").strip()
    if deployed_sha:
        _add(
            blockers,
            bool(source_sha and deployed_sha != source_sha),
            "deployed_sha does not match source_sha",
        )
    else:
        warnings.append("deployment identity not supplied; merge and deployment remain separate")

    requested_autonomy = run.get("requested_autonomy", "consultative")
    if requested_autonomy not in {"observe", "consultative", "shadow", "gated", "bounded"}:
        blockers.append("requested autonomy exceeds supported bounded modes")
    if requested_autonomy == "bounded" and stage != "bounded":
        blockers.append("bounded autonomy requires an explicit bounded stage")

    return _result(run, blockers, warnings)


def _result(run: dict[str, Any], blockers: list[str], warnings: list[str]) -> dict[str, Any]:
    ready = not blockers
    return {
        "schema_version": 1,
        "action_id": run.get("action_id"),
        "status": "review_ready" if ready else "hold",
        "may_merge_automatically": False,
        "may_deploy_automatically": False,
        "blockers": blockers,
        "warnings": warnings,
        "next_action": (
            "independent_human_review"
            if ready
            else "repair_evidence_and_re_evaluate"
        ),
    }
