"""Compact review cues; no inference, execution, permission or outcome verdict.

The full declarations stay in their sidecars. These summaries deliberately defer
operation-specific prose to the shared effect-review skill and the actual task.
"""

from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path, PurePosixPath

from skills.capabilities.effects import inspect_effects, validate_contract
from skills.capabilities.observations import digest, summarize, validate_report

METHOD = "skills/effect-review/SKILL.md"
_LIST_SECTIONS = {"preconditions", "expected_effects", "downstream_effects", "reuse"}
_SECTIONS = _LIST_SECTIONS | {"reversibility", "retry", "required_scope", "analysis"}
_INDEX = re.compile(r"0|[1-9][0-9]{0,8}")


def read_details(skill_dir: Path, selectors: list[str], *,
                 expected_id: str | None = None, expected_sha256: str | None = None) -> dict:
    """Read exact sections/list entries from one freshly inspected declaration.

    Selectors are explicit /section or /list_section/index paths, not searches.
    Invalid selectors/digests are rejected before inspection. A supplied digest
    must match; unavailable, stale or incomplete selections return no fragments.
    """
    if not isinstance(selectors, list) or not 1 <= len(selectors) <= 16:
        raise ValueError("selectors must be a list of 1 to 16 explicit section paths")
    parsed = {}
    for selector in selectors:
        if not isinstance(selector, str) or len(selector) > 64:
            raise ValueError("invalid effects selector")
        parts = selector.split("/")
        if (len(parts) not in (2, 3) or parts[0] or parts[1] not in _SECTIONS
                or (len(parts) == 3 and (parts[1] not in _LIST_SECTIONS
                                         or not _INDEX.fullmatch(parts[2])))):
            raise ValueError("select /section or /list_section/index; wildcards and nested fields are unsupported")
        parsed[selector] = (parts[1], int(parts[2]) if len(parts) == 3 else None)
    if expected_sha256 is not None and (not isinstance(expected_sha256, str)
                                        or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256)):
        raise ValueError("expected_sha256 must be a lowercase SHA-256 hex digest")

    snapshot = inspect_effects(skill_dir, expected_id=expected_id)
    contract = snapshot.get("contract")
    actual = digest(contract) if contract is not None else None
    matches = actual == expected_sha256 if actual is not None and expected_sha256 is not None else None
    result = {"status": snapshot["status"], "selection_status": "unavailable",
              "capability_id": contract["capability_id"] if contract else None,
              "declaration_sha256": actual, "matches_expected": matches,
              "error_count": len(snapshot["errors"]), "selected": {}}
    if matches is False:
        result["selection_status"] = "changed"
        return result
    if snapshot["status"] != "declared":
        return result
    missing = [selector for selector, (section, index) in parsed.items()
               if index is not None and index >= len(contract[section])]
    if missing:
        result["selection_status"] = "not_found"
        result["missing_selectors"] = missing
        return result
    result["selected"] = {selector: deepcopy(contract[section] if index is None else contract[section][index])
                          for selector, (section, index) in parsed.items()}
    result["selection_status"] = "selected"
    return result


def read_bundled_details(source: str, selectors: list[str], *,
                         expected_sha256: str | None = None) -> dict:
    """MCP entry: only canonical bundled skills/<...>/SKILL.md paths.

    External trees use the Python/CLI entry with a caller-supplied expected ID.
    This entry independently derives identity; sidecar claims never choose it.
    """
    from skills.capabilities.registry import REPO_ROOT
    if not isinstance(source, str) or not source or "\\" in source or ":" in source:
        raise ValueError("source must be a canonical bundled SKILL.md path")
    path = PurePosixPath(source)
    if (path.is_absolute() or len(path.parts) < 3 or path.parts[0] != "skills"
            or path.name != "SKILL.md" or ".." in path.parts or path.as_posix() != source):
        raise ValueError("source must be a canonical skills/<name>/SKILL.md path")
    root = REPO_ROOT.resolve()
    directory = root.joinpath(*path.parts[:-1])
    try:
        if directory.resolve() != directory:
            raise ValueError("source directory aliases are unsupported; use its canonical bundled path")
    except (OSError, RuntimeError) as exc:
        raise ValueError("source directory cannot be resolved") from exc
    identity = "zedarvates/botte-secrete:" + path.parent.as_posix()
    return read_details(directory, selectors, expected_id=identity, expected_sha256=expected_sha256)


def before(snapshot: dict | None, *, source: str | None = None) -> dict:
    """Project an inspector result, retaining its independently selected source.

    A supplied snapshot is trusted caller data, not an attestation. This function
    does not read a path, refresh hashes or resolve identity on the caller's behalf.
    """
    snapshot = snapshot or {}
    status = snapshot.get("status", "not_inspected")
    contract = snapshot.get("contract")
    if status not in {"missing", "invalid", "stale", "declared", "not_inspected"}:
        status = "invalid"
    if status in {"declared", "stale"} and validate_contract(contract):
        status = "invalid"
    if status not in {"declared", "stale"}:
        contract = None
    attention = [] if status == "declared" else ["declaration_" + status]
    result = {
        "source": source,
        "declaration": status,
        "capability_id": contract["capability_id"] if contract else None,
        "declaration_sha256": digest(contract) if contract else None,
        "reversibility": contract["reversibility"]["status"] if contract else "unknown",
        "retry": contract["retry"]["semantics"] if contract else "unknown",
        "attention": attention,
        "operation_assessment": "deferred",
    }
    if contract:
        if result["reversibility"] != "read_only":
            attention.append("check_operation_scope_and_recovery")
        if result["retry"] != "idempotent":
            attention.append("check_before_retry")
        if any(e["likelihood"] == "unknown" for field in
               ("expected_effects", "downstream_effects") for e in contract[field]):
            attention.append("unknown_effects")
        if contract["analysis"]["uncertainties"]:
            attention.append("declared_uncertainties")
        result["detail_counts"] = {field: len(contract[field]) for field in
                                   ("preconditions", "expected_effects", "downstream_effects", "reuse")}
    return result


def after(result: dict, prior: dict) -> dict:
    """Review a process result and any retained, validated observation companion.

    Only structural signals and observed facets are summarized. A successful
    process or HTTP response never promotes task success or reuse validation.
    """
    not_run = result.get("status") in {"blocked", "skipped"}
    attention = []
    review = {
        "coverage": "not_run" if not_run else "not_observed",
        "task_outcome": "not_run" if not_run else "unverified",
        "declaration_changed": None,
        "attention": attention,
        "next_action": "review_plan" if not_run else "verify_outcome_before_reuse",
    }
    if result.get("status") == "failed":
        attention.append("process_failed")
        review["next_action"] = "inspect_state_before_retry"
    observed = result.get("effects_observed")
    if observed is None:
        return review
    if validate_report(observed):
        review["coverage"] = "invalid_evidence"
        attention.append("invalid_observation_report")
        return review
    review["evidence_ref"] = "effects_observed"  # sibling in the same result
    review["coverage"] = "not_run" if not_run else "partial"
    summary = summarize(observed)
    review["observed_counts"] = {key: value for key, value in summary.items()
                                 if isinstance(value, int) and value}
    if observed["problems"]:
        attention.append("observation_problems")
    if summary["deviations"] or summary["failed_writes"]:
        attention.append("write_deviation")
    if summary["raised_calls"] or summary["network_failures"]:
        attention.append("nested_failure")
    if summary["unfinished_calls"] or summary["unfinished_network"]:
        attention.append("unfinished_work")
    if summary["unknown_write_facets"]:
        attention.append("unknown_write_facets")
    if summary["next_action"] == "inspect_partial_state_before_retry":
        review["next_action"] = "inspect_state_before_retry"
    matches = [c for c in observed["calls"]
               if prior.get("capability_id") and c["capability_id"] == prior["capability_id"]]
    if matches:
        review["declaration_changed"] = any(
            c["declaration_ref"] != prior.get("declaration_sha256")
            or c["declaration_status"] != prior.get("declaration") for c in matches)
        if review["declaration_changed"]:
            attention.append("declaration_changed")
    return review


def attach_results(results: list[dict], prior: list[dict | None]) -> None:
    """Attach reviews to their step by position, preserving repeated names."""
    for result, snapshot in zip(results, prior):
        if snapshot is not None:
            result["review_before"] = deepcopy(snapshot)
            result["review_after"] = after(result, snapshot)
