"""Read-only review of declared remaining work against a bound checkpoint.

This report is neither an execution plan nor a checkpoint migration.  Local
file predicates are rechecked here; the existing executor must check them
again when resuming the unchanged original execution plan.
"""

from __future__ import annotations

import hashlib
import sys
from copy import deepcopy
from pathlib import Path

from skills.conductor.handoff import _canonical_json, validate_plan_handoff
from skills.conductor.preferences import (
    METRICS, _canonical_digest, _validate, rank_plans,
)
from skills.conductor.verified import (
    MAX_DOCUMENT, MAX_REPORT, RUN_SCHEMA, STATES, _check, _decode_json,
    _digest, _passed, _resolve, _sources, read_document, validate_plan,
)

REQUEST_SCHEMA = "parcimonia.plan-replanning/v1"
RESULT_SCHEMA = "parcimonia.plan-replanning-report/v1"
MAX_INPUT_BYTES = MAX_DOCUMENT
MAX_DIAGNOSTICS = 64
MAX_GOALS_PER_REASON = 8
ADDITIVE_METRICS = tuple(metric for metric in METRICS if metric != "peak_ram_gib")
STRUCTURAL_REJECTIONS = {"unknown_action", "dependency_not_preceding",
                         "goals_not_declared", "project_has_no_action"}
LIMITATIONS = (
    "Checkpoint content bindings do not authenticate its author or history.",
    "Checks cover declared local files only, without an atomic filesystem snapshot.",
    "Sources, goals, command semantics and user or execution authority are unverified.",
    "Current processes, resource use and external effects are unobserved.",
    "Costs are declared estimates; validation overhead and sunk costs are excluded.",
    "A new candidate is execution-unqualified and cannot use the old checkpoint.",
    "Actual resume must use the unchanged old execution plan and recheck all evidence.",
)


def _contract(action: dict) -> dict:
    # The existing request treats these lists as sets.  Preserve every other
    # value, including provenance and JSON number/boolean distinctions.
    return {"id": action["id"], "needs": sorted(action["needs"]),
            "projects": sorted(action["projects"]),
            "provenance": action["provenance"]}


def _same_contract(left: dict, right: dict) -> bool:
    return _digest(_contract(left)) == _digest(_contract(right))


def _raw_checkpoint(root: Path, path: str) -> bytes:
    target = _resolve(root, path)
    if not target.is_file():
        raise ValueError("checkpoint must be a regular file")
    with target.open("rb") as stream:
        data = stream.read(MAX_REPORT + 1)
    if len(data) > MAX_REPORT:
        raise ValueError("checkpoint exceeds size limit")
    return data


def _checkpoint(root: Path, path: str, plan: dict) -> tuple[dict, str, str]:
    raw = _raw_checkpoint(root, path)
    checkpoint = read_document(_resolve(root, path), limit=MAX_REPORT)
    _canonical_json(checkpoint, "checkpoint", MAX_REPORT)
    if _digest(_decode_json(raw)) != _digest(checkpoint):
        raise ValueError("checkpoint changed during review")
    context = _digest({"root": str(root), "context": plan["context"],
                       "python": sys.version, "executable": sys.executable})
    if (type(checkpoint) is not dict or checkpoint.get("schema") != RUN_SCHEMA
            or checkpoint.get("plan_sha256") != _digest(plan)
            or checkpoint.get("context_sha256") != context):
        raise ValueError("checkpoint plan, context or schema does not match")
    rows = checkpoint.get("results")
    if (type(rows) is not list or not all(type(row) is dict for row in rows)
            or [row.get("id") for row in rows] != [step["id"] for step in plan["steps"]]):
        raise ValueError("invalid checkpoint step IDs or order")
    for row in rows:
        status, started, code = row.get("status"), row.get("started"), row.get("exit_code")
        if (type(status) is not str or status not in STATES
                or type(started) is not bool or "exit_code" not in row
                or (code is not None and type(code) is not int)):
            raise ValueError("invalid checkpoint step types")
        if not started:
            valid = status in {"pending", "blocked", "skipped"} and code is None
        else:
            valid = (status in {"running", "verified", "unverified", "failed", "uncertain", "stale"}
                     and (status != "running" or code is None)
                     and (status not in {"verified", "unverified", "stale"} or code == 0)
                     and (status != "failed" or (code is not None and code != 0)))
        if not valid:
            raise ValueError("inconsistent checkpoint step state")
    # Match the executor's separation between checkpoint and observed resources.
    target = _resolve(root, path)
    forbidden = {target, target.with_name(target.name + ".lock")}
    for step in plan["steps"]:
        paths = [*step["observes"], *step["source_hashes"],
                 *(check["path"] for check in step["requires"] + step["ensures"])]
        if any(_resolve(root, observed) in forbidden for observed in paths):
            raise ValueError("checkpoint must be separate from observed resources")
    return checkpoint, hashlib.sha256(raw).hexdigest(), context


class _Diagnostics:
    def __init__(self):
        self.items = []
        self.counts = {}
        self.total = 0

    def add(self, code: str, **detail):
        self.total += 1
        self.counts[code] = self.counts.get(code, 0) + 1
        if len(self.items) < MAX_DIAGNOSTICS:
            self.items.append({"code": code, **detail})


def _checks_summary(checks: list, group: str, aid: str, diagnostics: _Diagnostics) -> dict:
    for index, check in enumerate(checks):
        if not check["passed"]:
            diagnostics.add("local_check_failed", action_id=aid, group=group,
                            check_index=index, unknown=check["observed"]["state"] == "unknown")
    return {"checked": len(checks), "passed": sum(check["passed"] for check in checks),
            "failed": sum(not check["passed"] for check in checks),
            "unknown": sum(check["observed"]["state"] == "unknown" for check in checks)}


def _compact_reasons(reasons: list) -> list:
    compact = []
    for reason in reasons:
        item = deepcopy(reason)
        if "goals" in item:
            goals = item["goals"]
            item.update(goals=goals[:MAX_GOALS_PER_REASON], goal_count=len(goals),
                        goals_omitted=max(0, len(goals) - MAX_GOALS_PER_REASON))
        compact.append(item)
    return compact


def _step_states(root: Path, plan: dict, checkpoint: dict, previous: dict,
                 current: dict, diagnostics: _Diagnostics) -> tuple[list, set]:
    states, reusable = [], set()
    for step, row in zip(plan["steps"], checkpoint["results"]):
        aid = step["id"]
        present = aid in current
        unchanged = present and _same_contract(previous[aid], current[aid])
        state = {"id": aid, "checkpoint_status": row["status"], "started": row["started"],
                 "current_action_contract": "unchanged" if unchanged else "changed" if present else "absent",
                 "state": "unstarted", "reuse_eligible": False,
                 "local_checks": {}, "reasons": []}
        if row["started"]:
            state["state"] = "reconciliation_required"
            if row["status"] != "verified":
                state["reasons"].append("started_work_unresolved")
            else:
                groups = {"preconditions": _check(root, step["requires"]),
                          "postconditions": _check(root, step["ensures"]),
                          "sources": _sources(root, step)}
                for group, checks in groups.items():
                    state["local_checks"][group] = _checks_summary(checks, group, aid, diagnostics)
                    if not _passed(checks):
                        state["reasons"].append(group + "_failed")
                if not groups["postconditions"]:
                    state["reasons"].append("postconditions_missing")
                if any(dependency not in reusable for dependency in step["needs"]):
                    state["reasons"].append("dependency_not_reusable")
            if present and not unchanged:
                state["reasons"].append("started_action_contract_changed")
            if not state["reasons"]:
                reusable.add(aid)
                state["state"] = "reusable"
                state["reuse_eligible"] = unchanged
            else:
                diagnostics.add("reconciliation_required", action_id=aid,
                                reasons=list(state["reasons"]))
        states.append(state)
    return states, reusable


def _resume_compatible(candidate: dict, current: dict, previous: dict, handoff: dict) -> bool:
    old = handoff["selection_receipt"]["selected_plan"]
    projects = [{"id": project["id"], "goals": sorted(project["goals"])}
                for project in sorted(current["projects"], key=lambda project: project["id"])]
    goals = {pid: sorted(goals) for pid, goals in candidate["goals"].items()}
    old_actions = {action["id"]: action for action in previous["actions"]}
    actions = {action["id"]: action for action in current["actions"]}
    return (candidate["id"] == handoff["selected_candidate_id"]
            and candidate["steps"] == old["steps"]
            and _digest(goals) == _digest(old["goals"])
            and _digest(projects) == _digest(old["projects"])
            and all(aid in actions and _same_contract(old_actions[aid], actions[aid])
                    for aid in old["steps"]))


def review_plan_replanning(envelope: dict, checkpoint_path: str, *, cwd: str = ".") -> dict:
    """Review remaining allowances without executing or modifying anything.

    The strict envelope is at most 1 MiB.  A checkpoint is at most the existing
    executor's 32 MiB bound.  Invalid inputs or a changing checkpoint raise
    ValueError; no advisory reuse certificate is returned in those cases.
    """
    try:
        _canonical_json(envelope, "replanning envelope", MAX_INPUT_BYTES)
        if (type(envelope) is not dict
                or set(envelope) != {"schema", "previous_request", "previous_handoff",
                                     "current_request", "budget_scope"}
                or envelope["schema"] != REQUEST_SCHEMA
                or envelope["budget_scope"] != "remaining_work"):
            raise ValueError("expected strict remaining_work replanning envelope")
        previous, current = envelope["previous_request"], envelope["current_request"]
        handoff = validate_plan_handoff(previous, envelope["previous_handoff"])
        projects, actions, candidates, _ = _validate(current)
        plan = handoff["execution_plan"]
        validate_plan(plan)
        root = Path(cwd).resolve(strict=True)
        if not root.is_dir():
            raise ValueError("project must be a directory")
        checkpoint, checkpoint_digest, context_digest = _checkpoint(root, checkpoint_path, plan)
        diagnostics = _Diagnostics()
        previous_actions = {action["id"]: action for action in previous["actions"]}
        states, reusable = _step_states(root, plan, checkpoint, previous_actions, actions, diagnostics)
        unresolved = {state["id"] for state in states if state["state"] == "reconciliation_required"}
        blocked = set(unresolved)
        # Bounded fixed point also handles invalid/cyclic declared current DAGs;
        # the ordinary comparator still rejects their ordering independently.
        for _ in range(len(actions)):
            addition = {aid for aid, action in actions.items() if set(action["needs"]) & blocked} - blocked
            if not addition:
                break
            blocked.update(addition)
        reusable_current = {aid for aid in reusable if aid in actions
                            and _same_contract(previous_actions[aid], actions[aid])}
        review_digest = _digest(envelope)
        comparison = deepcopy(current)
        for action in comparison["actions"]:
            if action["id"] in reusable_current:
                for metric in ADDITIVE_METRICS:
                    action["metrics"][metric] = 0
                action["provenance"] = {"kind": "estimate", "ref":
                    f"replanning-proof:{review_digest}:{checkpoint_digest}:{action['id']}"}
        comparison["candidates"] = [candidate for candidate in comparison["candidates"]
                                    if not set(candidate["steps"]) & blocked]
        if comparison["candidates"]:
            # Validate the caller's original order before the internal cost
            # projection.  Moving reusable work must never repair an invalid
            # dependency order or change its rejection into eligibility.
            original = rank_plans(comparison)
            structurally_rejected = {report["id"] for report in original["candidates"]
                                     if STRUCTURAL_REJECTIONS & report["reason_counts"].keys()}
            del original
            for candidate in comparison["candidates"]:
                if candidate["id"] not in structurally_rejected:
                    # Reusable dependencies are recursively reusable too.  A
                    # zero-cost prefix therefore preserves valid ordering of
                    # all remaining work, while project completion ends at
                    # its last remaining beneficiary (or zero if finished).
                    # This copy never becomes a request, plan or checkpoint.
                    steps = candidate["steps"]
                    candidate["steps"] = [aid for aid in steps if aid in reusable_current] + [
                        aid for aid in steps if aid not in reusable_current]
            ranking = rank_plans(comparison)
            compared = {report["id"]: report for report in ranking["candidates"]}
            ranked_ids, recommended = ranking["ranking"], ranking["winner"]
        else:
            compared, ranked_ids, recommended = {}, [], None
        reports = []
        for candidate in sorted(candidates, key=lambda candidate: candidate["id"]):
            cid = candidate["id"]
            withheld = [aid for aid in candidate["steps"] if aid in blocked]
            compatible = _resume_compatible(candidate, current, previous, handoff)
            report = {"id": cid, "status": "withheld", "rank": None,
                      "recommended": cid == recommended,
                      "reused_action_ids": [aid for aid in candidate["steps"] if aid in reusable_current],
                      "remaining_action_ids": [aid for aid in candidate["steps"] if aid not in reusable_current],
                      "resume_compatible": compatible,
                      "execution_status": "resume_compatible" if compatible else "execution_unqualified"}
            if withheld:
                report.update(execution_status="reconciliation_required",
                              reasons=[{"code": "reconciliation_required", "action_id": aid}
                                       for aid in withheld[:MAX_DIAGNOSTICS]],
                              reason_counts={"reconciliation_required": len(withheld)},
                              reasons_omitted=max(0, len(withheld) - MAX_DIAGNOSTICS),
                              incremental_totals={metric: None for metric in METRICS},
                              incremental_project_totals={pid: {metric: None for metric in METRICS}
                                                          for pid in sorted(projects)})
            else:
                evaluated = compared[cid]
                report.update({key: deepcopy(evaluated[key]) for key in
                               ("status", "reason_counts", "reasons_omitted")})
                report.update(reasons=_compact_reasons(evaluated["reasons"]),
                              incremental_totals=evaluated["totals"],
                              incremental_project_totals=evaluated["project_totals"])
                if cid in ranked_ids:
                    report["rank"] = ranked_ids.index(cid) + 1
            reports.append(report)
        if hashlib.sha256(_raw_checkpoint(root, checkpoint_path)).hexdigest() != checkpoint_digest:
            raise ValueError("checkpoint changed during review")
        result = {
            "schema": RESULT_SCHEMA,
            "status": "reconciliation_required" if unresolved else "reviewed",
            "review_input_digest": review_digest, "current_input_digest": _canonical_digest(current),
            "previous_input_digest": handoff["input_digest"], "previous_handoff_id": handoff["handoff_id"],
            "previous_execution_plan_sha256": handoff["execution_plan_sha256"],
            "checkpoint_sha256": checkpoint_digest, "checkpoint_document_sha256": _digest(checkpoint),
            "context_sha256": context_digest, "budget_scope": "remaining_work",
            "cost_scope": {"additive_metrics": list(ADDITIVE_METRICS),
                           "reusable_additive_future_cost": 0,
                           "peak_ram": "declared_peak_retained_for_all_actions",
                           "project_elapsed_minutes": "remaining_serial_prefix_to_last_remaining_beneficiary_or_zero",
                           "candidate_order": "original_validated_before_internal_cost_projection_only",
                           "limits": "current_declared_remaining_allowances",
                           "sunk_costs_subtracted": False, "validation_overhead_included": False,
                           "provenance": "estimate_bound_to_review_input_checkpoint_and_step_checks"},
            "step_states": states, "reconciliation_required": bool(unresolved),
            "reconciliation_action_ids": [state["id"] for state in states if state["id"] in unresolved],
            "candidates": reports, "ranking": ranked_ids,
            "recommended_candidate_id": recommended, "selected_candidate_id": None,
            "selection_status": "not_selected", "execution_authorized": False,
            "diagnostics": diagnostics.items, "diagnostic_counts": dict(sorted(diagnostics.counts.items())),
            "diagnostics_omitted": diagnostics.total - len(diagnostics.items),
            "detail_caps": {"diagnostics": MAX_DIAGNOSTICS,
                            "reasons_per_candidate": MAX_DIAGNOSTICS,
                            "goals_per_reason": MAX_GOALS_PER_REASON},
            "claim": {"local_checks_recomputed": True, "checkpoint_authenticated": False,
                      "source_verified": False, "goal_coverage_verified": False,
                      "choice_authority_verified": False, "resources_observed": False,
                      "measured_gain": None},
            "boundaries": {"execution": False, "checkpoint_write": False,
                           "checkpoint_migration": False, "models": False, "network": False},
            "limitations": list(LIMITATIONS),
        }
        _canonical_json(result, "replanning report", MAX_REPORT)
        return result
    except (OSError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError) as exc:
        raise ValueError("invalid replanning input, checkpoint or project") from exc
