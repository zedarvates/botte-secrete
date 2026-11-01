"""Rank supplied serial plans using declared user priorities and hard limits.

Pure stdlib: no action generation, execution, model calls, telemetry or I/O.
Inputs and goal coverage are declarations, not independently verified facts.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from decimal import Context, Decimal, localcontext
from typing import Any

REQUEST_SCHEMA = "parcimonia.plan-preferences/v1"
RESULT_SCHEMA = "parcimonia.plan-ranking/v1"
MAX_INPUT_BYTES = 1024 * 1024
MAX_METRIC_VALUE = 10 ** 15
MAX_REASONS_PER_CANDIDATE = 64
METRICS = (
    "elapsed_minutes", "human_minutes", "money", "tokens", "energy_wh",
    "peak_ram_gib",
)
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}\Z")


def _fail(message: str) -> None:
    raise ValueError(message)


def _object(value: Any, required: set[str], optional: set[str], path: str) -> dict:
    if type(value) is not dict:
        _fail(f"{path}: expected an object")
    if not all(type(key) is str for key in value):
        _fail(f"{path}: keys must be strings")
    missing = required - value.keys()
    extra = value.keys() - required - optional
    if missing or extra:
        _fail(f"{path}: missing {sorted(missing)}, unknown {sorted(extra)}")
    return value


def _list(value: Any, path: str, maximum: int, minimum: int = 0) -> list:
    if type(value) is not list or not minimum <= len(value) <= maximum:
        _fail(f"{path}: expected {minimum}..{maximum} items")
    return value


def _identifier(value: Any, path: str) -> str:
    if type(value) is not str or not _ID.fullmatch(value):
        _fail(f"{path}: expected a short ASCII identifier")
    return value


def _ids(value: Any, path: str, maximum: int, minimum: int = 0) -> list[str]:
    values = _list(value, path, maximum, minimum)
    for item in values:
        _identifier(item, path)
    if len(values) != len(set(values)):
        _fail(f"{path}: duplicate identifiers")
    return values


def _number(value: Any, path: str, *, nullable: bool = False) -> None:
    if value is None and nullable:
        return
    if type(value) not in (int, float):
        _fail(f"{path}: expected a nonnegative finite number")
    if not 0 <= value <= MAX_METRIC_VALUE or (type(value) is float and not math.isfinite(value)):
        _fail(f"{path}: expected a number between 0 and {MAX_METRIC_VALUE}")


def _reject_constant(value: str) -> None:
    _fail(f"non-finite JSON number: {value}")


def _parse_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        _fail("non-finite JSON number")
    return parsed


def _unique_object(pairs: list[tuple[str, Any]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            _fail(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _check_json_depth(raw: str) -> None:
    # Limit nesting before the JSON decoder recurses. Brackets in strings do
    # not count; syntax validity remains the decoder's responsibility.
    depth = 0
    in_string = False
    escaped = False
    for char in raw:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
            if depth > 64:
                _fail("request exceeds 64 nesting levels")
        elif char in "]}":
            depth -= 1


def _check_python_json(value: Any) -> None:
    stack = [(value, 0)]
    while stack:
        item, depth = stack.pop()
        if depth > 64:
            _fail("request exceeds 64 nesting levels")
        if type(item) is dict:
            if not all(type(key) is str for key in item):
                _fail("JSON object keys must be strings")
            stack.extend((child, depth + 1) for child in item.values())
        elif type(item) is list:
            stack.extend((child, depth + 1) for child in item)
        elif type(item) not in (str, int, float, bool, type(None)):
            _fail("request must contain only JSON data")


def parse_request_json(raw: str) -> dict:
    """Parse bounded strict JSON; reject duplicate keys and non-finite numbers.

    Structural/semantic validation is performed separately by ``rank_plans``.
    """
    if type(raw) is not str:
        _fail("request JSON must be text")
    try:
        if len(raw.encode("utf-8")) > MAX_INPUT_BYTES:
            _fail("request exceeds 1 MiB UTF-8")
        _check_json_depth(raw)
        request = json.loads(
            raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant,
            parse_float=_parse_float,
        )
    except (UnicodeError, RecursionError, OverflowError) as exc:
        raise ValueError("invalid request JSON") from exc
    if type(request) is not dict:
        _fail("request JSON must contain an object")
    return request


def _validate(request: Any) -> tuple[dict, dict, list, dict]:
    # Bound direct Python callers as well as the JSON entry point. allow_nan
    # rejects NaN/Infinity even in unused fields before structural validation.
    _check_python_json(request)
    try:
        size = len(json.dumps(request, allow_nan=False, ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError, UnicodeError, RecursionError, OverflowError) as exc:
        raise ValueError("request must be finite JSON data") from exc
    if size > MAX_INPUT_BYTES:
        _fail("request exceeds 1 MiB UTF-8")
    _object(request, {"schema", "currency", "projects", "actions", "candidates", "preferences"}, set(), "request")
    if request["schema"] != REQUEST_SCHEMA:
        _fail(f"schema must be {REQUEST_SCHEMA}")
    if type(request["currency"]) is not str or not re.fullmatch(r"[A-Z]{3}", request["currency"]):
        _fail("currency: expected a three-letter uppercase code")

    projects: dict[str, dict] = {}
    for project in _list(request["projects"], "projects", 32, 1):
        _object(project, {"id", "goals"}, set(), "project")
        pid = _identifier(project["id"], "project.id")
        _ids(project["goals"], "project.goals", 64, 1)
        if pid in projects:
            _fail(f"duplicate project: {pid}")
        projects[pid] = project

    actions: dict[str, dict] = {}
    for action in _list(request["actions"], "actions", 256, 1):
        _object(action, {"id", "needs", "projects", "metrics", "provenance"}, set(), "action")
        aid = _identifier(action["id"], "action.id")
        if aid in actions:
            _fail(f"duplicate action: {aid}")
        _ids(action["needs"], "action.needs", 256)
        beneficiaries = _ids(action["projects"], "action.projects", 32, 1)
        if set(beneficiaries) - projects.keys():
            _fail(f"action {aid}: unknown project")
        _object(action["metrics"], set(METRICS), set(), "action.metrics")
        for metric, value in action["metrics"].items():
            _number(value, f"action.metrics.{metric}", nullable=True)
        provenance = _object(action["provenance"], {"kind", "ref"}, set(), "action.provenance")
        if provenance["kind"] not in ("estimate", "measurement"):
            _fail("action.provenance.kind: expected estimate or measurement")
        if type(provenance["ref"]) is not str or not 1 <= len(provenance["ref"]) <= 512:
            _fail("action.provenance.ref: expected 1..512 characters")
        actions[aid] = action

    candidates = _list(request["candidates"], "candidates", 64, 1)
    seen: set[str] = set()
    for candidate in candidates:
        _object(candidate, {"id", "steps", "goals"}, set(), "candidate")
        cid = _identifier(candidate["id"], "candidate.id")
        if cid in seen:
            _fail(f"duplicate candidate: {cid}")
        seen.add(cid)
        _ids(candidate["steps"], "candidate.steps", 256)
        goals = _object(candidate["goals"], set(), set(projects), "candidate.goals")
        for pid, values in goals.items():
            _ids(values, f"candidate.goals.{pid}", 64)
            if set(values) - set(projects[pid]["goals"]):
                _fail(f"candidate {cid}: unknown goal for {pid}")

    preferences = _object(request["preferences"], {"priorities"}, {"limits", "project_limits"}, "preferences")
    priorities = _list(preferences["priorities"], "preferences.priorities", 64, 1)
    chosen: set[tuple[str | None, str]] = set()
    for priority in priorities:
        _object(priority, {"metric"}, {"project"}, "priority")
        metric = priority["metric"]
        if type(metric) is not str or metric not in METRICS:
            _fail("priority.metric: unknown metric")
        if "project" in priority:
            _identifier(priority["project"], "priority.project")
            if priority["project"] not in projects:
                _fail("priority.project: unknown project")
        key = (priority.get("project"), metric)
        if key in chosen:
            _fail("duplicate priority")
        chosen.add(key)

    limits = _object(preferences.get("limits", {}), set(), set(METRICS), "preferences.limits")
    for metric, value in limits.items():
        _number(value, f"preferences.limits.{metric}")
    project_limits = _object(preferences.get("project_limits", {}), set(), set(projects), "preferences.project_limits")
    for pid, values in project_limits.items():
        _object(values, set(), set(METRICS), f"preferences.project_limits.{pid}")
        for metric, value in values.items():
            _number(value, f"preferences.project_limits.{pid}.{metric}")
    return projects, actions, candidates, preferences


def _canonical_digest(request: dict) -> str:
    # Catalogues and set-like lists have no ranking semantics; priority order
    # and candidate step order do, and are intentionally retained.
    canonical = json.loads(json.dumps(request))
    canonical["projects"].sort(key=lambda item: item["id"])
    for project in canonical["projects"]:
        project["goals"].sort()
    canonical["actions"].sort(key=lambda item: item["id"])
    for action in canonical["actions"]:
        action["needs"].sort()
        action["projects"].sort()
    canonical["candidates"].sort(key=lambda item: item["id"])
    for candidate in canonical["candidates"]:
        for goals in candidate["goals"].values():
            goals.sort()
    payload = json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _aggregate(selected: list[dict]) -> dict[str, Decimal | None]:
    totals: dict[str, Decimal | None] = {}
    for metric in METRICS:
        values = [action["metrics"][metric] for action in selected]
        if any(value is None for value in values):
            totals[metric] = None
        else:
            numbers = [Decimal(str(value)) for value in values]
            totals[metric] = max(numbers, default=Decimal(0)) if metric == "peak_ram_gib" else sum(numbers, Decimal(0))
    return totals


def _public_number(value: Decimal | None) -> int | float | None:
    if value is None:
        return None
    return int(value) if value == value.to_integral_value() else float(value)


def _public_totals(totals: dict[str, Decimal | None]) -> dict:
    return {metric: _public_number(value) for metric, value in totals.items()}


class _ReasonSummary:
    """Count every cause but retain only a bounded, stable diagnostic sample."""

    def __init__(self) -> None:
        self.retained: list[dict] = []
        self.counts: dict[str, int] = {}
        self.rejected_count = 0
        self.unknown_count = 0
        self.total_count = 0

    def add(self, reason: dict, *, unknown: bool = False) -> None:
        code = reason["code"]
        self.counts[code] = self.counts.get(code, 0) + 1
        self.total_count += 1
        if unknown:
            self.unknown_count += 1
        else:
            self.rejected_count += 1
        if len(self.retained) < MAX_REASONS_PER_CANDIDATE:
            self.retained.append(reason)


def _evaluate(candidate: dict, projects: dict, actions: dict, preferences: dict) -> tuple[dict, tuple]:
    reasons = _ReasonSummary()
    unknown_action = False
    selected = []
    completed: set[str] = set()
    for aid in candidate["steps"]:
        if aid not in actions:
            unknown_action = True
            reasons.add({"code": "unknown_action", "action": aid})
            continue
        action = actions[aid]
        for dependency in sorted(action["needs"]):
            if dependency not in completed:
                reasons.add({"code": "dependency_not_preceding", "action": aid, "dependency": dependency})
        completed.add(aid)
        selected.append(action)

    for pid in sorted(projects):
        missing = sorted(set(projects[pid]["goals"]) - set(candidate["goals"].get(pid, [])))
        if missing:
            reasons.add({"code": "goals_not_declared", "project": pid, "goals": missing})
        if not any(pid in action["projects"] for action in selected):
            reasons.add({"code": "project_has_no_action", "project": pid})

    totals = {metric: None for metric in METRICS} if unknown_action else _aggregate(selected)
    project_totals = {}
    for pid in sorted(projects):
        project_actions = [action for action in selected if pid in action["projects"]]
        metrics = _aggregate(project_actions)
        # Completion is elapsed time since the whole serial plan began,
        # including work for other projects preceding this project's last step.
        last = max((index for index, action in enumerate(selected) if pid in action["projects"]), default=-1)
        metrics["elapsed_minutes"] = _aggregate(selected[:last + 1])["elapsed_minutes"]
        project_totals[pid] = {metric: None for metric in METRICS} if unknown_action else metrics

    required: set[tuple[str | None, str]] = set()
    for priority in preferences["priorities"]:
        required.add((priority.get("project"), priority["metric"]))
    for metric, limit in sorted(preferences.get("limits", {}).items()):
        required.add((None, metric))
        value = totals[metric]
        if value is not None and value > Decimal(str(limit)):
            reasons.add({"code": "limit_exceeded", "metric": metric, "limit": limit})
    for pid, limits in sorted(preferences.get("project_limits", {}).items()):
        for metric, limit in sorted(limits.items()):
            required.add((pid, metric))
            value = project_totals[pid][metric]
            if value is not None and value > Decimal(str(limit)):
                reasons.add({"code": "limit_exceeded", "project": pid, "metric": metric, "limit": limit})

    unknown_metrics = []
    for pid, values in [(None, totals), *project_totals.items()]:
        for metric in METRICS:
            if values[metric] is None:
                item = {"metric": metric}
                if pid is not None:
                    item["project"] = pid
                unknown_metrics.append(item)
                if (pid, metric) in required:
                    reasons.add({"code": "required_cost_unknown", **item}, unknown=True)

    status = "rejected" if reasons.rejected_count else "undetermined" if reasons.unknown_count else "eligible"
    priority_values = tuple(
        (project_totals[priority["project"]] if "project" in priority else totals)[priority["metric"]]
        for priority in preferences["priorities"]
    )
    shared = sorted(action["id"] for action in selected if len(action["projects"]) > 1)
    return {
        "id": candidate["id"], "status": status,
        "reasons": reasons.retained,
        "reason_counts": dict(sorted(reasons.counts.items())),
        "reasons_omitted": reasons.total_count - len(reasons.retained),
        "reasons_truncated": reasons.total_count > len(reasons.retained),
        "totals": _public_totals(totals),
        "project_totals": {pid: _public_totals(values) for pid, values in project_totals.items()},
        "unknown_metrics": unknown_metrics,
        "shared_actions": shared,
        "goal_coverage": "declared_unverified",
    }, priority_values


def rank_plans(request: dict) -> dict:
    """Validate and rank candidates by lexicographic minimisation.

    Hard limits precede preferences. Candidates whose required costs are
    unknown remain undetermined. All output costs and goals are unverified
    caller declarations, even when a provenance kind says ``measurement``.
    """
    projects, actions, candidates, preferences = _validate(request)
    # Positive finite input floats range down to 5e-324, while the metric
    # upper bound is 1e15. This precision retains even their smallest addends
    # across the bounded 256-step plan and ignores caller decimal settings.
    with localcontext(Context(prec=350)):
        evaluated = [_evaluate(candidate, projects, actions, preferences)
                     for candidate in sorted(candidates, key=lambda item: item["id"])]
    eligible = [(report, values) for report, values in evaluated if report["status"] == "eligible"]
    eligible.sort(key=lambda pair: (pair[1], pair[0]["id"]))
    frontier = []
    for report, values in eligible:
        dominated = any(
            all(other_value <= value for other_value, value in zip(other, values))
            and any(other_value < value for other_value, value in zip(other, values))
            for other_report, other in eligible if other_report["id"] != report["id"]
        )
        if not dominated:
            frontier.append(report["id"])
    undetermined = [report["id"] for report, _ in evaluated if report["status"] == "undetermined"]
    ranking = [report["id"] for report, _ in eligible]
    return {
        "schema": RESULT_SCHEMA,
        "status": "ranked" if ranking else "undetermined" if undetermined else "no_eligible_plan",
        "input_digest": _canonical_digest(request),
        "winner": ranking[0] if ranking else None,
        "ranking": ranking,
        "pareto_frontier": sorted(frontier),
        "remaining_unknown_candidates": undetermined,
        "candidates": [report for report, _ in evaluated],
        "currency": request["currency"],
        "priorities": [dict(priority) for priority in preferences["priorities"]],
        "method": "lexicographic_minimisation_with_hard_limits",
        "planning_model": "serial_declared_metrics",
        "project_cost_allocation": "full_beneficiary_cost_not_additive_across_projects",
        "project_elapsed_minutes": "time_from_plan_start_to_last_beneficiary_action",
        "optimality_scope": "known_eligible_candidates_only",
        "claim": {"source_verified": False, "goal_coverage_verified": False,
                  "universal_optimality": False, "measured_gain": None},
        "boundaries": {"models": False, "network": False, "execution": False,
                       "collection": False, "storage": False},
    }
