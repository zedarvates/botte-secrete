"""Bounded measurement hints from one-factor endpoint sensitivity.

Pure advisory stdlib: no questions are asked and no measurements, selection,
execution, model calls or I/O occur. Endpoint changes are not probabilities or
expected values of information; interacting uncertainty can remain unresolved.
"""

from __future__ import annotations

from copy import deepcopy

from .preferences import rank_plans
from .uncertainty import analyse_plan_uncertainty

RESULT_SCHEMA = "parcimonia.plan-measurements/v1"
MAX_UNKNOWN_CONTEXTS = 64
_PRIORITY = {"choice_change": 0, "eligibility_change": 1, "required_unknown": 2}


def _budget(value: int, name: str, maximum: int) -> None:
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f"{name}: expected an integer between 1 and {maximum}")


def _dependencies(comparison: dict, possible: set[str]) -> dict:
    """Index only action metrics that feed required candidate aggregates."""
    actions = {item["id"]: item for item in comparison["actions"]}
    preferences = comparison["preferences"]
    required = {(item.get("project"), item["metric"])
                for item in preferences["priorities"]}
    required.update((None, metric) for metric in preferences.get("limits", {}))
    required.update((pid, metric)
                    for pid, limits in preferences.get("project_limits", {}).items()
                    for metric in limits)
    dependencies: dict = {}
    for candidate in comparison["candidates"]:
        if candidate["id"] not in possible:
            continue
        selected = [actions[aid] for aid in candidate["steps"]]
        for pid, metric in required:
            if pid is None:
                affected = selected
            elif metric == "elapsed_minutes":
                last = max((index for index, action in enumerate(selected)
                            if pid in action["projects"]), default=-1)
                affected = selected[:last + 1]
            else:
                affected = [action for action in selected if pid in action["projects"]]
            for action in affected:
                dependency = dependencies.setdefault((action["id"], metric),
                                                     {"candidates": set(), "scopes": set()})
                dependency["candidates"].add(candidate["id"])
                dependency["scopes"].add((pid, metric))
    return dependencies


def _context(key: tuple[str, str], dependency: dict) -> dict:
    return {
        "action_id": key[0], "metric": key[1],
        "affected_candidate_ids": sorted(dependency["candidates"]),
        "required_for": [
            {"metric": metric, **({"project": pid} if pid is not None else {})}
            for pid, metric in sorted(dependency["scopes"], key=lambda item: (item[0] or "", item[1]))
        ],
    }


def suggest_plan_measurements(request: dict, max_checks: int = 32,
                              max_questions: int = 8) -> dict:
    """Suggest bounded checks for the strict plan-uncertainty envelope.

    A check probes one active ranged variable twice, with every other metric
    left nominal. Budgets are API parameters, never fields added to the strict
    envelope. Required unknown costs without ranges remain unknown, not zero.
    """
    _budget(max_checks, "max_checks", 128)
    _budget(max_questions, "max_questions", 16)
    uncertainty = analyse_plan_uncertainty(request)
    # The public analyser validates the envelope once. Fresh snapshots prevent
    # probes or returned hints from changing any caller-owned nested value.
    comparison = deepcopy(request["comparison_request"])
    actions = {item["id"]: item for item in comparison["actions"]}
    reports = {item["id"]: item for item in uncertainty["candidates"]}
    possible = {cid for cid, item in reports.items()
                if item["structural_status"] == "valid"
                and item["budget_status"] != "exceeds_declared_limit"}
    dependencies = _dependencies(comparison, possible)
    ranges = {(item["action_id"], item["metric"]): item for item in uncertainty["ranges"]}
    active_ranges = [key for key in sorted(ranges) if key in dependencies
                     and (ranges[key]["lower"] != ranges[key]["upper"]
                          or actions[key[0]]["metrics"][key[1]] is None)]
    checked, omitted = active_ranges[:max_checks], active_ranges[max_checks:]
    nominal_winner = uncertainty["nominal_recommended_candidate_id"]
    suggestions = []
    for key in checked:
        interval = ranges[key]
        endpoints = {}
        for bound in ("lower", "upper"):
            probe = deepcopy(comparison)
            action = next(item for item in probe["actions"] if item["id"] == key[0])
            action["metrics"][key[1]] = interval[bound]
            action["provenance"] = {"kind": "estimate",
                                    "ref": f"one-factor-{bound}:{uncertainty['input_digest']}"}
            endpoints[bound] = rank_plans(probe)
        lower, upper = endpoints["lower"], endpoints["upper"]
        choice_changes = len({nominal_winner, lower["winner"], upper["winner"]}) > 1
        statuses = {bound: {item["id"]: item["status"] for item in result["candidates"]}
                    for bound, result in endpoints.items()}
        changes = []
        for cid in sorted(dependencies[key]["candidates"]):
            nominal_status = reports[cid]["nominal_status"]
            if len({nominal_status, statuses["lower"][cid], statuses["upper"][cid]}) > 1:
                changes.append({"candidate_id": cid, "nominal": nominal_status,
                                "lower": statuses["lower"][cid], "upper": statuses["upper"][cid]})
        if not choice_changes and not changes:
            continue
        suggestions.append({
            "kind": "choice_change" if choice_changes else "eligibility_change",
            **_context(key, dependencies[key]),
            "nominal_value": actions[key[0]]["metrics"][key[1]],
            "range": {"lower": interval["lower"], "upper": interval["upper"],
                      "provenance": deepcopy(interval["provenance"])},
            "recommended_candidate_ids": {"nominal": nominal_winner,
                                          "lower": lower["winner"], "upper": upper["winner"]},
            "choice_changes": choice_changes, "eligibility_changes": changes,
            "method": "one_factor_endpoint_sensitivity",
        })
    unknown = [key for key in sorted(dependencies) if key not in ranges
               and actions[key[0]]["metrics"][key[1]] is None]
    suggestions.sort(key=lambda item: (_PRIORITY[item["kind"]], item["action_id"], item["metric"]))
    questions = suggestions[:max_questions]
    # Count all unknowns, but expand only the questions actually retained.
    # The exhaustive index below stays compact even for 1,536 unknown metrics.
    for key in unknown[:max_questions - len(questions)]:
        questions.append({
            "kind": "required_unknown", **_context(key, dependencies[key]),
            "nominal_value": None, "range": None,
            "reason": "A required aggregate is unknown; obtain a value or a justified range to complete comparison.",
            "method": "required_unknown_dependency",
        })
    question_omissions = len(suggestions) + len(unknown) - len(questions)
    unknown_context_keys = unknown[:MAX_UNKNOWN_CONTEXTS]
    unknown_context_omissions = len(unknown) - len(unknown_context_keys)
    robust_id = uncertainty["robust_recommended_candidate_id"]
    if questions:
        status = "measurement_suggestions"
    elif omitted:
        status = "analysis_incomplete"
    elif robust_id is not None:
        status = "robust_recommendation_no_decision_changing_question"
    else:
        status = "no_one_factor_endpoint_change_detected"
    return {
        "schema": RESULT_SCHEMA, "status": status,
        "input_digest": uncertainty["input_digest"],
        "comparison_input_digest": uncertainty["comparison_input_digest"],
        "nominal_comparison": deepcopy(uncertainty["nominal_comparison"]),
        "nominal_recommended_candidate_id": nominal_winner,
        "robust_recommended_candidate_id": robust_id,
        "selected_candidate_id": None, "selection_status": "not_selected",
        "questions": questions, "questions_omitted": question_omissions,
        "questions_truncated": bool(question_omissions),
        "analysis_incomplete": bool(omitted),
        "unresolved_required_unknowns": [{"action_id": key[0], "metric": key[1]} for key in unknown],
        "unresolved_required_unknown_count": len(unknown),
        "unresolved_required_unknown_contexts": [_context(key, dependencies[key]) for key in unknown_context_keys],
        "unresolved_required_unknown_contexts_omitted": unknown_context_omissions,
        "unresolved_required_unknown_contexts_truncated": bool(unknown_context_omissions),
        "analysis": {
            "method": "one_factor_endpoint_sensitivity", "max_checks": max_checks,
            "max_questions": max_questions, "active_ranged_variables": len(active_ranges),
            "variables_checked": len(checked), "endpoint_rank_calls": 2 * len(checked),
            "variables_omitted": len(omitted),
            "omitted_variables": [{"action_id": key[0], "metric": key[1]} for key in omitted],
            "complete": not omitted, "joint_uncertainty_evaluated": False,
            "decision_stability_certified": robust_id is not None,
        },
        "claim": {"source_verified": False, "ranges_verified": False,
                  "expected_value_of_information": None, "probabilities_assumed": False,
                  "joint_uncertainty_may_remain": robust_id is None and bool(active_ranges or unknown),
                  "universal_optimality": False, "measured_gain": None},
        "limitations": [
            "Each endpoint probe changes one variable while all other costs remain nominal.",
            "No endpoint change does not certify stability under interacting uncertainties.",
            "A robust certificate covers only supplied candidates and declared ranges.",
            "Unknown comparisons remain visible; required unknown costs are never zero-filled.",
        ],
        "boundaries": {"models": False, "network": False, "execution": False,
                       "collection": False, "storage": False, "selection": False,
                       "questions_asked": False},
    }
