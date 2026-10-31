"""Factory Assurance Layer.

The layer is intentionally deterministic. Models and agents may populate the
run record, but they do not decide whether evidence is sufficient for review.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .adapters import _hex_digest, _strict_json
from .roles import validate_assignment


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
    value = _strict_json(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("assurance run must be a JSON object")
    return value


def _non_empty_strings(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(
        isinstance(item, str) and item.strip() for item in value
    )


def _string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value)


def _add(blockers: list[str], condition: bool, message: str) -> None:
    if condition:
        blockers.append(message)


def _identity_ok(identity: dict[str, Any], warnings: list[str]) -> tuple[bool, str]:
    """Check declared candidate identity across direct or synthetic PR checkouts.

    Direct CI normally has source/build/tested commit equality. GitHub pull_request
    workflows may instead test a synthetic merge commit; in that case we require
    the source/build/tested Git tree SHA to be explicitly supplied and identical.
    This checks hash format/equality, not Git objects or evidence authenticity.
    """
    try:
        source_sha, build_sha, tested_sha = (
            _hex_digest(identity.get(key), 40, key) for key in ("source_sha", "build_sha", "tested_sha")
        )
    except ValueError:
        return False, "source/build/tested commit identity is incomplete or invalid"
    if len({source_sha, build_sha, tested_sha}) == 1:
        return True, "commit"

    try:
        source_tree, build_tree, tested_tree = (
            _hex_digest(identity.get(key), 40, key) for key in ("source_tree", "build_tree", "tested_tree")
        )
    except ValueError:
        return False, "source/build/tested identity mismatch; valid tree identity is required"
    if len({source_tree, build_tree, tested_tree}) == 1:
        warnings.append(
            "commit IDs differ but source/build/tested Git tree identity matches; "
            "declared hashes still require independent verification against Git objects"
        )
        return True, "tree"
    return False, "source/build/tested identity mismatch"


def evaluate_assurance(run: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a run record and return a stable, auditable decision.

    This function never returns an instruction to merge or deploy. A successful
    evaluation only means that the record is ready for independent human review.
    """
    blockers: list[str] = []
    warnings: list[str] = []

    if not isinstance(run, dict):
        return _result({}, ["assurance run must be an object"], warnings)
    missing = sorted(REQUIRED_TOP_LEVEL - set(run))
    _add(blockers, bool(missing), f"missing top-level fields: {', '.join(missing)}")
    if missing:
        return _result(run, blockers, warnings)

    _add(blockers, type(run.get("schema_version")) is not int or run["schema_version"] != 1, "unsupported schema_version")
    stage = run.get("stage")
    _add(blockers, not isinstance(stage, str) or stage not in VALID_STAGES, "unsupported stage")
    for field in ("mission", "actors", "effects", "controls", "identity"):
        _add(blockers, not isinstance(run[field], dict), f"{field} must be an object")
    if blockers:
        return _result(run, blockers, warnings)

    mission = run.get("mission") or {}
    _add(blockers, not _non_empty_strings(mission.get("goals")), "mission.goals must be non-empty")
    _add(blockers, not _non_empty_strings(mission.get("invariants")), "mission.invariants must be non-empty")
    _add(blockers, not _string_list(mission.get("non_goals")), "mission.non_goals must be a list of strings")
    _add(
        blockers,
        not _string_list(mission.get("forbidden_transformations")),
        "mission.forbidden_transformations must be a list of strings",
    )
    _add(
        blockers,
        mission.get("within_mission") is not True,
        "mission boundary is not positively established",
    )

    actors = run.get("actors") or {}
    builder = actors.get("builder")
    judge = actors.get("judge")
    orchestrator = actors.get("orchestrator")
    builder = builder.strip() if isinstance(builder, str) else ""
    judge = judge.strip() if isinstance(judge, str) else ""
    if orchestrator is not None and (not isinstance(orchestrator, str) or not orchestrator.strip()):
        blockers.append("orchestrator identity must be a non-empty string when supplied")
        orchestrator = None
    _add(blockers, not builder, "builder identity is missing")
    _add(blockers, not judge, "independent judge identity is missing")
    if builder and judge:
        for blocker in validate_assignment(builder=builder, judge=judge, orchestrator=orchestrator):
            if blocker not in blockers:
                blockers.append(blocker)

    effects = run.get("effects") or {}
    for field in ("declared", "observed", "unresolved"):
        _add(blockers, not _string_list(effects.get(field)), f"effects.{field} must be a list of strings")
    if any(not _string_list(effects.get(field)) for field in ("declared", "observed", "unresolved")):
        return _result(run, blockers, warnings)
    declared = set(effects["declared"])
    observed = set(effects["observed"])
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
            name = item.get("name")
            name = name.strip() if isinstance(name, str) else ""
            status = item.get("status")
            required = item.get("required", True)
            if not name:
                blockers.append("evidence item has no name")
            elif name in names:
                blockers.append(f"duplicate evidence item: {name}")
            names.add(name)
            if not isinstance(status, str) or status not in VALID_EVIDENCE_STATUS:
                blockers.append(f"evidence {name or '<unnamed>'} has invalid status")
            if type(required) is not bool:
                blockers.append(f"evidence {name or '<unnamed>'} required must be a boolean")
            if required and status != "pass":
                blockers.append(f"required evidence did not pass: {name or '<unnamed>'}")

    controls = run.get("controls") or {}
    _add(blockers, controls.get("positive_control") != "pass", "positive control must pass")
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
    if controls.get("historical_regressions_checked") is not True:
        warnings.append("historical regression corpus not checked")
    if controls.get("adversarial_cases_checked") is not True:
        warnings.append("randomized/adversarial cases not checked")

    identity = run.get("identity") or {}
    identity_valid, identity_reason = _identity_ok(identity, warnings)
    _add(blockers, not identity_valid, identity_reason)

    deployed_sha = identity.get("deployed_sha")
    if deployed_sha is not None and deployed_sha != "":
        try:
            source_sha = _hex_digest(identity.get("source_sha"), 40, "source_sha")
            deployed_sha = _hex_digest(deployed_sha, 40, "deployed_sha")
            _add(blockers, deployed_sha != source_sha, "deployed_sha does not match source_sha")
        except ValueError:
            blockers.append("deployment identity is invalid")
    else:
        warnings.append("deployment identity not supplied; merge and deployment remain separate")

    requested_autonomy = run.get("requested_autonomy", "consultative")
    if not isinstance(requested_autonomy, str) or requested_autonomy not in VALID_STAGES:
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
        "next_action": "independent_human_review" if ready else "repair_evidence_and_re_evaluate",
    }
