"""Conservative interval analysis for supplied serial plans and caller ranges.

Pure stdlib and advisory: no measurements, execution, model calls or selection.
The box certificate is sufficient, not necessary, including for shared costs.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from decimal import Context, Decimal, localcontext
from typing import Any

from .preferences import (
    MAX_INPUT_BYTES, METRICS, _aggregate, _canonical_digest, _check_python_json,
    _evaluate, _fail, _identifier, _list, _number, _object, _public_number,
    _public_totals, _validate, rank_plans,
)

REQUEST_SCHEMA = "parcimonia.plan-uncertainty/v1"
RESULT_SCHEMA = "parcimonia.plan-uncertainty-report/v1"


def _validate_uncertainty(request: Any) -> tuple[dict, dict, list, dict, list]:
    """Validate the complete bounded envelope without changing its inputs."""
    _check_python_json(request)
    try:
        size = len(json.dumps(request, allow_nan=False, ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError, UnicodeError, RecursionError, OverflowError) as exc:
        raise ValueError("request must be finite JSON data") from exc
    if size > MAX_INPUT_BYTES:
        _fail("request exceeds 1 MiB UTF-8")
    _object(request, {"schema", "comparison_request", "ranges"}, set(), "request")
    if request["schema"] != REQUEST_SCHEMA:
        _fail(f"schema must be {REQUEST_SCHEMA}")
    projects, actions, candidates, preferences = _validate(request["comparison_request"])
    ranges = []
    seen = set()
    for item in _list(request["ranges"], "ranges", 256 * len(METRICS)):
        _object(item, {"action_id", "metric", "lower", "upper", "provenance"}, set(), "range")
        aid = _identifier(item["action_id"], "range.action_id")
        if aid not in actions:
            _fail("range.action_id: unknown action")
        metric = item["metric"]
        if type(metric) is not str or metric not in METRICS:
            _fail("range.metric: unknown metric")
        key = (aid, metric)
        if key in seen:
            _fail("duplicate action/metric range")
        seen.add(key)
        _number(item["lower"], "range.lower")
        _number(item["upper"], "range.upper")
        lower, upper = Decimal(str(item["lower"])), Decimal(str(item["upper"]))
        if lower > upper:
            _fail("range.lower must not exceed range.upper")
        nominal = actions[aid]["metrics"][metric]
        if nominal is not None and not lower <= Decimal(str(nominal)) <= upper:
            _fail("range must contain the nominal metric")
        provenance = _object(item["provenance"], {"kind", "ref"}, set(), "range.provenance")
        if provenance["kind"] not in ("estimate", "measurement"):
            _fail("range.provenance.kind: expected estimate or measurement")
        if type(provenance["ref"]) is not str or not 1 <= len(provenance["ref"]) <= 512:
            _fail("range.provenance.ref: expected 1..512 characters")
        ranges.append(deepcopy(item))
    ranges.sort(key=lambda item: (item["action_id"], item["metric"]))
    return projects, actions, candidates, preferences, ranges


def apply_range_values(request: dict, bound: str) -> dict:
    """Return a fresh comparison request with supplied range endpoints applied.

    Unbounded null costs remain null. This helper never imputes a point cost.
    Projected actions carry estimate provenance bound to this envelope and bound,
    even for degenerate ranges; original measurements remain in the input.
    """
    if type(bound) is not str or bound not in ("lower", "upper"):
        _fail("bound must be lower or upper")
    _, _, _, _, ranges = _validate_uncertainty(request)
    comparison = deepcopy(request["comparison_request"])
    actions = {action["id"]: action for action in comparison["actions"]}
    projection_ref = f"uncertainty-{bound}:{_envelope_digest(request, ranges)}"
    for item in ranges:
        action = actions[item["action_id"]]
        action["metrics"][item["metric"]] = item[bound]
        action["provenance"] = {"kind": "estimate", "ref": projection_ref}
    return comparison


def _envelope_digest(request: dict, ranges: list) -> str:
    # The original comparison digest canonicalizes catalogue/set-like lists.
    # Normalize those same lists while preserving serial steps and priorities.
    comparison = deepcopy(request["comparison_request"])
    for project in comparison["projects"]:
        project["goals"].sort()
    comparison["projects"].sort(key=lambda item: item["id"])
    for action in comparison["actions"]:
        action["needs"].sort()
        action["projects"].sort()
    comparison["actions"].sort(key=lambda item: item["id"])
    for candidate in comparison["candidates"]:
        for goals in candidate["goals"].values():
            goals.sort()
    comparison["candidates"].sort(key=lambda item: item["id"])
    canonical = {"schema": REQUEST_SCHEMA, "comparison_request": comparison, "ranges": ranges}
    payload = json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _candidate_totals(candidate: dict, projects: dict, actions: dict) -> tuple[dict, dict]:
    if any(aid not in actions for aid in candidate["steps"]):
        unknown = {metric: None for metric in METRICS}
        return unknown, {pid: dict(unknown) for pid in sorted(projects)}
    selected = [actions[aid] for aid in candidate["steps"]]
    totals = _aggregate(selected)
    project_totals = {}
    for pid in sorted(projects):
        metrics = _aggregate([action for action in selected if pid in action["projects"]])
        last = max((index for index, action in enumerate(selected) if pid in action["projects"]), default=-1)
        metrics["elapsed_minutes"] = _aggregate(selected[:last + 1])["elapsed_minutes"]
        project_totals[pid] = metrics
    return totals, project_totals


def _priority_values(totals: dict, project_totals: dict, preferences: dict) -> tuple:
    return tuple((project_totals[item["project"]] if "project" in item else totals)[item["metric"]]
                 for item in preferences["priorities"])


def _budget_status(structural_status: str, lower: dict, upper: dict,
                   lower_projects: dict, upper_projects: dict, preferences: dict) -> str:
    if structural_status == "rejected":
        return "exceeds_declared_limit"
    uncertain = False
    limits = [(None, metric, value) for metric, value in sorted(preferences.get("limits", {}).items())]
    limits.extend((pid, metric, value)
                  for pid, values in sorted(preferences.get("project_limits", {}).items())
                  for metric, value in sorted(values.items()))
    for pid, metric, limit in limits:
        lower_value = (lower if pid is None else lower_projects[pid])[metric]
        upper_value = (upper if pid is None else upper_projects[pid])[metric]
        limit_value = Decimal(str(limit))
        if lower_value is not None and lower_value > limit_value:
            return "exceeds_declared_limit"
        if upper_value is None or upper_value > limit_value:
            uncertain = True
    return "uncertain_limits" if uncertain else "within_declared_limits"


def analyse_plan_uncertainty(request: dict) -> dict:
    """Analyse declared ranges and certify only conservative stable recommendations.

    Unknown costs have a domain lower bound of zero and an unknown upper bound;
    zero is never substituted into the caller's nominal comparison. Certificates
    apply only to supplied candidates, caller ranges and declared serial costs.
    """
    projects, actions, candidates, preferences, ranges = _validate_uncertainty(request)
    comparison = request["comparison_request"]
    nominal = rank_plans(comparison)
    nominal_statuses = {item["id"]: item["status"] for item in nominal["candidates"]}
    bounds = {(item["action_id"], item["metric"]): item for item in ranges}
    lower_actions, upper_actions = deepcopy(actions), deepcopy(actions)
    fully_unknown = []
    for aid, action in actions.items():
        for metric, nominal_value in action["metrics"].items():
            interval = bounds.get((aid, metric))
            if interval is not None:
                lower_actions[aid]["metrics"][metric] = interval["lower"]
                upper_actions[aid]["metrics"][metric] = interval["upper"]
            elif nominal_value is None:
                lower_actions[aid]["metrics"][metric] = 0
                fully_unknown.append({"action_id": aid, "metric": metric})
    fully_unknown.sort(key=lambda item: (item["action_id"], item["metric"]))
    reports, vectors = [], {}
    with localcontext(Context(prec=350)):
        for candidate in sorted(candidates, key=lambda item: item["id"]):
            structural, _ = _evaluate(candidate, projects, actions, {"priorities": []})
            structural_status = "rejected" if structural["status"] == "rejected" else "valid"
            lower, lower_projects = _candidate_totals(candidate, projects, lower_actions)
            upper, upper_projects = _candidate_totals(candidate, projects, upper_actions)
            lower_values = _priority_values(lower, lower_projects, preferences)
            upper_values = _priority_values(upper, upper_projects, preferences)
            unknown_priorities = [dict(item) for item, low, high in zip(preferences["priorities"], lower_values, upper_values)
                                  if low is None or high is None]
            budget_status = _budget_status(structural_status, lower, upper, lower_projects, upper_projects, preferences)
            report = {
                "id": candidate["id"], "structural_status": structural_status,
                "nominal_status": nominal_statuses[candidate["id"]],
                "structural_reasons": structural["reasons"],
                "structural_reason_counts": structural["reason_counts"],
                "structural_reasons_omitted": structural["reasons_omitted"],
                "budget_status": budget_status,
                "lower_totals": _public_totals(lower), "upper_totals": _public_totals(upper),
                "lower_project_totals": {pid: _public_totals(values) for pid, values in lower_projects.items()},
                "upper_project_totals": {pid: _public_totals(values) for pid, values in upper_projects.items()},
                "lower_priority_values": [_public_number(value) for value in lower_values],
                "upper_priority_values": [_public_number(value) for value in upper_values],
                "unknown_priority_metrics": unknown_priorities,
                "shared_actions": structural["shared_actions"],
                "goal_coverage": "declared_unverified", "robust_certificate": False,
            }
            reports.append(report)
            vectors[candidate["id"]] = (lower_values, upper_values)
        possible = [report for report in reports
                    if report["structural_status"] == "valid" and report["budget_status"] != "exceeds_declared_limit"]
        robust_id = None
        for candidate in possible:
            if candidate["budget_status"] != "within_declared_limits" or candidate["unknown_priority_metrics"]:
                continue
            upper_values = vectors[candidate["id"]][1]
            certified = all(
                not rival["unknown_priority_metrics"]
                and (upper_values, candidate["id"]) <= (vectors[rival["id"]][0], rival["id"])
                for rival in possible if rival["id"] != candidate["id"]
            )
            if certified:
                candidate["robust_certificate"] = True
                robust_id = candidate["id"]
    return {
        "schema": RESULT_SCHEMA, "input_digest": _envelope_digest(request, ranges),
        "comparison_input_digest": _canonical_digest(comparison),
        "nominal_recommended_candidate_id": nominal["winner"],
        "robust_recommended_candidate_id": robust_id,
        "selected_candidate_id": None, "selection_status": "not_selected",
        "nominal_comparison": {key: nominal[key] for key in (
            "status", "winner", "ranking", "remaining_unknown_candidates", "input_digest")},
        "candidates": reports, "ranges": ranges, "fully_unknown_costs": fully_unknown,
        "bound_assumptions": [
            "Unknown costs remain unknown; zero lower bounds are domain bounds, never point estimates.",
            "Supplied ranges are caller declarations; no probability distribution is assumed.",
            "Box comparison is sufficient and conservative, not necessary; shared costs may be correlated.",
        ],
        "currency": comparison["currency"],
        "priorities": deepcopy(preferences["priorities"]),
        "method": "conservative_lexicographic_box_certificate_with_id_tiebreak",
        "planning_model": "serial_declared_metrics",
        "project_cost_allocation": "full_beneficiary_cost_not_additive_across_projects",
        "project_elapsed_minutes": "time_from_plan_start_to_last_beneficiary_action",
        "certificate_scope": "supplied_candidates_and_declared_ranges_only",
        "claim": {"source_verified": False, "ranges_verified": False,
                  "goal_coverage_verified": False, "universal_optimality": False,
                  "measured_gain": None},
        "boundaries": {"models": False, "network": False, "execution": False,
                       "collection": False, "storage": False, "selection": False},
    }
