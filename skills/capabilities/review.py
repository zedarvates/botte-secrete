"""Compact review cues; no inference, execution, permission or outcome verdict.

The full declarations stay in their sidecars. These summaries deliberately defer
operation-specific prose to the shared effect-review skill and the actual task.
"""

from __future__ import annotations

from copy import deepcopy

from skills.capabilities.effects import validate_contract
from skills.capabilities.observations import digest, summarize, validate_report

METHOD = "skills/effect-review/SKILL.md"


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
