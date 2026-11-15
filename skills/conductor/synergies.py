"""Compare explicitly supplied cross-project sharing alternatives.

One action ID always retains one canonical contract.  Complete baseline and
shared candidates are supplied by the caller; this module never substitutes
actions, rewrites dependencies or infers semantic equivalence from similarity.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from decimal import Context, Decimal, localcontext
from typing import Any

from skills.conductor.handoff import _canonical_json
from skills.conductor.preferences import (
    MAX_INPUT_BYTES, METRICS, _aggregate, _identifier,
    _ids, _list, _object, _public_totals, _validate, rank_plans,
)
from skills.conductor.uncertainty import _candidate_totals

REQUEST_SCHEMA = "parcimonia.plan-synergies/v1"
RESULT_SCHEMA = "parcimonia.plan-synergies-report/v1"
MAX_OPPORTUNITIES = 32
MAX_REPORT_BYTES = 2 * MAX_INPUT_BYTES
MAX_REASONS = 8
MAX_GOALS_PER_REASON = 4
MAX_CHANGED_ACTIONS = 32
STRUCTURAL_REJECTIONS = frozenset({
    "unknown_action", "dependency_not_preceding", "goals_not_declared",
    "project_has_no_action",
})
LIMITATIONS = (
    "Sharing equivalence, source authenticity and goal coverage are caller declarations, not verified facts.",
    "Whole-candidate differences include all changed actions and ordering, not only the declared sharing group.",
    "Group costs describe only the listed actions and do not establish causal savings or a feasible standalone subplan.",
    "Costs follow the existing serial declared model; RAM is a maximum, not a live-resource measurement.",
    "Negative shared-minus-baseline cost means a declared reduction, not measured savings or a guarantee.",
    "Unknown costs remain unknown; comparison overhead and unlisted costs are excluded.",
    "Recommendations do not select a plan or grant execution authority; a trusted controller supplies commands and checks.",
)


def _validate_request(envelope: Any) -> tuple[dict, dict, list, list]:
    _canonical_json(envelope, "synergies envelope", MAX_INPUT_BYTES)
    _object(envelope, {"schema", "comparison_request", "opportunities"}, set(), "request")
    if envelope["schema"] != REQUEST_SCHEMA:
        raise ValueError(f"schema must be {REQUEST_SCHEMA}")
    comparison = envelope["comparison_request"]
    projects, actions, candidates, _ = _validate(comparison)
    by_id = {candidate["id"]: candidate for candidate in candidates}
    opportunities, ids, bindings = [], set(), set()
    for item in _list(envelope["opportunities"], "opportunities", MAX_OPPORTUNITIES):
        _object(item, {"id", "baseline_candidate_id", "shared_candidate_id",
                       "separate_action_ids", "shared_action_id", "assumption_ref"}, set(), "opportunity")
        oid = _identifier(item["id"], "opportunity.id")
        if oid in ids:
            raise ValueError("duplicate opportunity id")
        ids.add(oid)
        baseline_id = _identifier(item["baseline_candidate_id"], "opportunity.baseline_candidate_id")
        shared_id = _identifier(item["shared_candidate_id"], "opportunity.shared_candidate_id")
        if baseline_id not in by_id or shared_id not in by_id or baseline_id == shared_id:
            raise ValueError("opportunity must bind two distinct known candidates")
        members = _ids(item["separate_action_ids"], "opportunity.separate_action_ids", 256, 2)
        shared_action = _identifier(item["shared_action_id"], "opportunity.shared_action_id")
        if any(aid not in actions for aid in [*members, shared_action]):
            raise ValueError("opportunity must bind known actions")
        reference = item["assumption_ref"]
        if type(reference) is not str or not 1 <= len(reference) <= 512:
            raise ValueError("opportunity.assumption_ref: expected 1..512 characters")
        baseline, shared = by_id[baseline_id], by_id[shared_id]
        baseline_steps, shared_steps = set(baseline["steps"]), set(shared["steps"])
        if (not set(members) <= baseline_steps or shared_action in baseline_steps
                or shared_action not in shared_steps or set(members) & shared_steps):
            raise ValueError("opportunity actions contradict baseline/shared candidate membership")
        if any(set(baseline["goals"].get(pid, [])) != set(shared["goals"].get(pid, []))
               for pid in projects):
            raise ValueError("opportunity candidates must declare the same goals per project")
        beneficiaries = set().union(*(set(actions[aid]["projects"]) for aid in members))
        if len(beneficiaries) < 2 or set(actions[shared_action]["projects"]) != beneficiaries:
            raise ValueError("shared action projects must equal the multi-project member union")
        binding = (baseline_id, shared_id, tuple(sorted(members)), shared_action)
        if binding in bindings:
            raise ValueError("duplicate opportunity binding")
        bindings.add(binding)
        opportunities.append({**deepcopy(item), "separate_action_ids": sorted(members)})
    opportunities.sort(key=lambda item: item["id"])
    return projects, actions, candidates, opportunities


def _input_digest(comparison_digest: str, opportunities: list) -> str:
    canonical = {"schema": REQUEST_SCHEMA, "comparison_input_digest": comparison_digest,
                 "opportunities": opportunities}
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _delta(baseline: dict, shared: dict, *, qualified: bool) -> tuple[dict, dict]:
    # Subtract exact Decimal aggregates before the public int/float conversion.
    # Subtracting already rounded JSON totals can erase a real small difference.
    exact = {metric: shared[metric] - baseline[metric]
             if qualified and shared[metric] is not None and baseline[metric] is not None
             else None for metric in METRICS}
    public = _public_totals(exact)
    rounded = {metric: str(value) for metric, value in exact.items()
               if value is not None and Decimal(str(public[metric])) != value}
    return public, rounded


def _compact_reason(reason: dict) -> dict:
    sample = deepcopy(reason)
    if "goals" in sample:
        goals = sample["goals"]
        sample.update(goals=goals[:MAX_GOALS_PER_REASON], goal_count=len(goals),
                      goals_omitted=max(0, len(goals) - MAX_GOALS_PER_REASON))
    return sample


def _changes(ids: set) -> dict:
    ordered = sorted(ids)
    return {"ids": ordered[:MAX_CHANGED_ACTIONS], "count": len(ordered),
            "omitted": max(0, len(ordered) - MAX_CHANGED_ACTIONS)}


def _intern_rounding(rounded: dict, exact_values: list, indices: dict) -> dict:
    references = {}
    for metric, value in rounded.items():
        if value not in indices:
            indices[value] = len(exact_values)
            exact_values.append(value)
        references[metric] = indices[value]
    return references


def analyse_plan_synergies(envelope: dict) -> dict:
    """Compare full supplied plans under explicit unverified sharing assumptions.

    The strict input is bounded to 1 MiB and the compact JSON report to 2 MiB.
    Raises ValueError for contradictory bindings, malformed data or an output
    exceeding its byte budget, without returning a partial report. Structural
    invalidity remains advisory evidence with null deltas, rather than being
    repaired by dependency rewrites or hidden action substitutions.
    """
    projects, actions, candidates, opportunities = _validate_request(envelope)
    comparison = envelope["comparison_request"]
    ranking = rank_plans(comparison)
    ranks = {cid: index + 1 for index, cid in enumerate(ranking["ranking"])}
    by_id = {candidate["id"]: candidate for candidate in candidates}
    summaries, qualified = [], {}
    for report in ranking["candidates"]:
        cid = report["id"]
        qualified[cid] = not bool(STRUCTURAL_REJECTIONS & report["reason_counts"].keys())
        reason_count = sum(report["reason_counts"].values())
        summaries.append({key: deepcopy(report[key]) for key in
                          ("id", "status", "totals", "project_totals", "reason_counts")})
        summaries[-1].update(structural_status="valid" if qualified[cid] else "rejected",
                             rank=ranks.get(cid),
                             reasons=[_compact_reason(reason) for reason in report["reasons"][:MAX_REASONS]],
                             reasons_omitted=max(0, reason_count - MAX_REASONS))
    reports, exact_values, exact_indices = [], [], {}
    with localcontext(Context(prec=350)):
        # Reuse exactly the existing serial aggregation before public rounding.
        totals = {cid: _candidate_totals(candidate, projects, actions)
                  for cid, candidate in by_id.items()}
        for opportunity in opportunities:
            baseline_id, shared_id = opportunity["baseline_candidate_id"], opportunity["shared_candidate_id"]
            baseline, shared = by_id[baseline_id], by_id[shared_id]
            comparable = qualified[baseline_id] and qualified[shared_id]
            base_totals, base_projects = totals[baseline_id]
            shared_totals, shared_projects = totals[shared_id]
            separate_group = _aggregate([actions[aid] for aid in opportunity["separate_action_ids"]])
            shared_group = _aggregate([actions[opportunity["shared_action_id"]]])
            global_delta, global_rounding = _delta(base_totals, shared_totals, qualified=comparable)
            global_rounding = _intern_rounding(global_rounding, exact_values, exact_indices)
            project_deltas, project_rounding = {}, {}
            for pid in sorted(projects):
                project_deltas[pid], rounded = _delta(base_projects[pid], shared_projects[pid], qualified=comparable)
                if rounded:
                    project_rounding[pid] = _intern_rounding(rounded, exact_values, exact_indices)
            group_delta, group_rounding = _delta(separate_group, shared_group, qualified=comparable)
            group_rounding = _intern_rounding(group_rounding, exact_values, exact_indices)
            eligible = [cid for cid in ranking["ranking"] if cid in (baseline_id, shared_id)]
            reports.append({
                **deepcopy(opportunity), "status": "compared" if comparable else "unqualified",
                "preferred_eligible_candidate_id": eligible[0] if comparable and eligible else None,
                "global_delta": global_delta,
                "project_deltas": project_deltas,
                "group_metrics": {"separate_totals": _public_totals(separate_group),
                                  "shared_totals": _public_totals(shared_group),
                                  "delta": group_delta,
                                  "scope": "declared_group_actions_only"},
                "delta_rounding": {"global": global_rounding, "projects": project_rounding,
                                   "group": group_rounding},
                "action_changes": {"added": _changes(set(shared["steps"]) - set(baseline["steps"])),
                                   "removed": _changes(set(baseline["steps"]) - set(shared["steps"]))},
                "attribution_to_sharing_verified": False,
            })
    result = {
        "schema": RESULT_SCHEMA, "status": "analysed",
        "input_digest": _input_digest(ranking["input_digest"], opportunities),
        "comparison_input_digest": ranking["input_digest"], "currency": ranking["currency"],
        "ranking": ranking["ranking"], "recommended_candidate_id": ranking["winner"],
        "remaining_unknown_candidates": ranking["remaining_unknown_candidates"],
        "optimality_scope": ranking["optimality_scope"],
        "preferences": deepcopy(comparison["preferences"]),
        "selected_candidate_id": None, "selection_status": "not_selected",
        "candidates": summaries, "opportunities": reports,
        "delta_convention": "shared_minus_baseline",
        "exact_delta_values": exact_values,
        "delta_publication": "Numeric deltas may round; delta_rounding contains integer indices into exact_delta_values for affected values only, including underflows. Each indexed value is an exact signed Decimal string. Empty maps mean no numeric information was lost.",
        "comparison_scope": "whole_candidates_with_all_action_and_order_changes",
        "planning_model": ranking["planning_model"],
        "project_cost_allocation": ranking["project_cost_allocation"],
        "project_elapsed_minutes": ranking["project_elapsed_minutes"],
        "detail_caps": {"opportunities": MAX_OPPORTUNITIES, "candidate_reasons": MAX_REASONS,
                        "goals_per_reason": MAX_GOALS_PER_REASON, "changed_action_ids": MAX_CHANGED_ACTIONS},
        "claims": {"equivalence_verified": False, "source_verified": False,
                   "goal_coverage_verified": False, "attribution_to_sharing_verified": False,
                   "universal_optimality": False, "measured_gain": None},
        "boundaries": {"execution": False, "selection": False, "models": False,
                       "network": False, "collection": False, "storage": False,
                       "catalogue_rewrite": False},
        "execution_authorized": False, "limitations": list(LIMITATIONS),
    }
    _canonical_json(result, "synergies report", MAX_REPORT_BYTES)
    return result
