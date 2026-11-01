"""Build bounded serial candidates from caller-supplied goal recipes.

Recipes declare alternative methods; they do not prove that actions achieve
goals. This pure stdlib module generates action identifiers and dependency
order only, without commands, model calls, execution, collection or I/O.
"""

from __future__ import annotations

import hashlib
import heapq
import itertools
import json
from collections import OrderedDict
from copy import deepcopy
from typing import Any

from skills.conductor.preferences import (
    MAX_INPUT_BYTES, REQUEST_SCHEMA as PREFERENCES_SCHEMA,
    _check_python_json, _identifier, _ids, _list, _object, _validate,
    parse_request_json,
)

REQUEST_SCHEMA = "parcimonia.recipe-planning/v1"
RESULT_SCHEMA = "parcimonia.recipe-candidates/v1"
PLANNING_VERSION = "catalogue_dependency_closure/v1"
MAX_RECIPES = 1024
MAX_DIAGNOSTICS = 64
DEFAULT_MAX_CANDIDATES = 16
DEFAULT_MAX_EXPANSIONS = 256
MAX_CANDIDATES = 64
MAX_EXPANSIONS = 4096
MAX_CLOSURE_CACHE = 64


def _json_size(value: Any) -> int:
    try:
        return len(json.dumps(value, allow_nan=False, ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError, UnicodeError, RecursionError, OverflowError) as exc:
        raise ValueError("request must be finite JSON data") from exc


def _limit(request: dict, name: str, default: int, maximum: int) -> int:
    value = request.get(name, default)
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f"{name}: expected an integer between 1 and {maximum}")
    return value


def _validate_request(request: Any) -> tuple[dict, dict, dict, int, int]:
    _check_python_json(request)
    if _json_size(request) > MAX_INPUT_BYTES:
        raise ValueError("request exceeds 1 MiB UTF-8")
    _object(request, {"schema", "currency", "projects", "actions", "recipes", "preferences"},
            {"max_candidates", "max_expansions"}, "request")
    if request["schema"] != REQUEST_SCHEMA:
        raise ValueError(f"schema must be {REQUEST_SCHEMA}")
    max_candidates = _limit(request, "max_candidates", DEFAULT_MAX_CANDIDATES, MAX_CANDIDATES)
    max_expansions = _limit(request, "max_expansions", DEFAULT_MAX_EXPANSIONS, MAX_EXPANSIONS)

    # Reuse the exact structural contracts, without evaluating declared costs
    # or treating an unknown metric as an invalid recipe.
    # Validate the independent identifier lists with the same helpers, then
    # use a smaller projection for the shared validator. Otherwise inserting
    # its required dummy candidate could push an exactly 1 MiB recipe request
    # over its size bound, despite the original request already being bounded.
    project_items = _list(request["projects"], "projects", 32, 1)
    for project in project_items:
        _object(project, {"id", "goals"}, set(), "project")
        _ids(project["goals"], "project.goals", 64, 1)
    action_items = _list(request["actions"], "actions", 256, 1)
    for action in action_items:
        _object(action, {"id", "needs", "projects", "metrics", "provenance"}, set(), "action")
        _ids(action["needs"], "action.needs", 256)
    comparison = {key: request[key] for key in ("currency", "preferences")}
    comparison["projects"] = [{**project, "goals": project["goals"][:1]} for project in project_items]
    comparison["actions"] = [{**action, "needs": []} for action in action_items]
    comparison.update(schema=PREFERENCES_SCHEMA,
                      candidates=[{"id": "validation", "steps": [], "goals": {}}])
    _validate(comparison)
    projects = {project["id"]: project for project in project_items}
    actions = {action["id"]: action for action in action_items}
    recipes: dict[str, dict] = {}
    for recipe in _list(request["recipes"], "recipes", MAX_RECIPES):
        _object(recipe, {"id", "project", "goal", "actions"}, set(), "recipe")
        rid = _identifier(recipe["id"], "recipe.id")
        if rid in recipes:
            raise ValueError(f"duplicate recipe: {rid}")
        pid = _identifier(recipe["project"], "recipe.project")
        goal = _identifier(recipe["goal"], "recipe.goal")
        if pid not in projects:
            raise ValueError(f"recipe {rid}: unknown project")
        if goal not in projects[pid]["goals"]:
            raise ValueError(f"recipe {rid}: unknown goal for {pid}")
        for aid in _ids(recipe["actions"], "recipe.actions", 256, 1):
            if aid not in actions:
                raise ValueError(f"recipe {rid}: unknown action {aid}")
            if pid not in actions[aid]["projects"]:
                raise ValueError(f"recipe {rid}: action {aid} does not benefit project {pid}")
        recipes[rid] = recipe
    return projects, actions, recipes, max_candidates, max_expansions


def _canonical_request(request: dict) -> dict:
    canonical = deepcopy(request)
    canonical["projects"].sort(key=lambda item: item["id"])
    for project in canonical["projects"]:
        project["goals"].sort()
    canonical["actions"].sort(key=lambda item: item["id"])
    for action in canonical["actions"]:
        action["needs"].sort()
        action["projects"].sort()
    canonical["recipes"].sort(key=lambda item: item["id"])
    for recipe in canonical["recipes"]:
        recipe["actions"].sort()
    return canonical


def _digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class _Diagnostics:
    """Count all encountered causes while retaining a bounded stable sample."""

    def __init__(self) -> None:
        self.items: list[dict] = []
        self.counts: dict[str, int] = {}
        self.total = 0

    def add(self, code: str, **details: Any) -> None:
        self.total += 1
        self.counts[code] = self.counts.get(code, 0) + 1
        if len(self.items) < MAX_DIAGNOSTICS:
            self.items.append({"code": code, **details})


    def merge(self, counts: dict[str, int], samples: list[dict], *, combination: int) -> None:
        """Apply cached graph counts without rebuilding discarded diagnostics."""
        self.total += sum(counts.values())
        for code, count in counts.items():
            self.counts[code] = self.counts.get(code, 0) + count
        remaining = MAX_DIAGNOSTICS - len(self.items)
        self.items.extend({**sample, "combination": combination} for sample in samples[:remaining])


def _ordered_closure(required: frozenset[str], actions: dict) -> tuple[list[str], dict[str, int], list[dict]]:
    closure: set[str] = set()
    pending = sorted(required, reverse=True)
    while pending:
        aid = pending.pop()
        if aid in closure:
            continue
        closure.add(aid)
        for dependency in sorted(actions[aid]["needs"], reverse=True):
            if dependency in actions and dependency not in closure:
                pending.append(dependency)

    # Each action and its unique needs are visited once. Count every missing
    # edge, but never materialise a diagnostic dictionary beyond the sample.
    # Sorting after closure discovery preserves the original diagnostic order.
    missing_count = 0
    missing_samples = []
    for aid in sorted(closure):
        for dependency in sorted(actions[aid]["needs"]):
            if dependency not in actions:
                missing_count += 1
                if len(missing_samples) < MAX_DIAGNOSTICS:
                    missing_samples.append({"code": "missing_dependency", "action": aid,
                                            "dependency": dependency})
    if missing_count:
        return [], {"missing_dependency": missing_count}, missing_samples

    # Kahn's algorithm gives the lexically first available action at each
    # serial step. Catalogue and recipe listing order has no effect.
    indegrees = {aid: len(actions[aid]["needs"]) for aid in closure}
    consumers: dict[str, list[str]] = {aid: [] for aid in closure}
    for aid in sorted(closure):
        for dependency in actions[aid]["needs"]:
            consumers[dependency].append(aid)
    ready = [aid for aid, count in indegrees.items() if count == 0]
    heapq.heapify(ready)
    ordered = []
    while ready:
        aid = heapq.heappop(ready)
        ordered.append(aid)
        for consumer in consumers[aid]:
            indegrees[consumer] -= 1
            if indegrees[consumer] == 0:
                heapq.heappush(ready, consumer)
    if len(ordered) != len(closure):
        # Residual actions can include consumers blocked by a cycle. Do not
        # claim that every listed action itself belongs to a cycle.
        return [], {"dependency_cycle": 1}, [
            {"code": "dependency_cycle", "blocked_actions": sorted(closure - set(ordered))}]
    return ordered, {}, []


def build_plan_candidates(request: dict) -> dict:
    """Choose one declared recipe per goal, close dependencies and order steps.

    Search visits sorted goals and sorted recipe IDs, counting every attempted
    combination including rejected and duplicate plans. It stops at explicit
    bounds and reports completeness only after exhausting that finite search.
    Equivalent action plans retain their first recipe combination. Neither a
    complete search nor a declared recipe establishes real goal feasibility.
    """
    projects, actions, recipes, max_candidates, max_expansions = _validate_request(request)
    canonical = _canonical_request(request)
    input_digest = _digest(canonical)
    comparison = {key: canonical[key] for key in ("currency", "projects", "actions", "preferences")}
    comparison.update(schema=PREFERENCES_SCHEMA, candidates=[])
    goals = [(pid, goal) for pid in sorted(projects) for goal in sorted(projects[pid]["goals"])]
    methods: dict[tuple[str, str], list[str]] = {goal: [] for goal in goals}
    for rid in sorted(recipes):
        recipe = recipes[rid]
        methods[(recipe["project"], recipe["goal"])].append(rid)
    diagnostics = _Diagnostics()
    for (pid, goal), alternatives in methods.items():
        if not alternatives:
            diagnostics.add("missing_recipe", project=pid, goal=goal)

    candidate_recipes: dict[str, list[str]] = {}
    known_steps: set[tuple[str, ...]] = set()
    # This cache belongs to this exact request only. Required action sets,
    # rather than recipe IDs, share work across equivalent method choices.
    # Evict before insertion so even transient cache size stays bounded.
    closure_cache: OrderedDict[frozenset[str], tuple[list[str], dict[str, int], list[dict]]] = OrderedDict()
    attempted = 0
    rejected = 0
    duplicates = 0
    truncation_reason = None
    declared_goals = {pid: sorted(projects[pid]["goals"]) for pid in sorted(projects)}
    if all(methods.values()):
        for selection in itertools.product(*(methods[goal] for goal in goals)):
            # Reaching a bound on the final combination remains complete;
            # seeing another unprocessed combination makes truncation explicit.
            if attempted >= max_expansions:
                truncation_reason = "max_expansions"
                break
            if len(candidate_recipes) >= max_candidates:
                truncation_reason = "max_candidates"
                break
            attempted += 1
            required = frozenset(aid for rid in selection for aid in recipes[rid]["actions"])
            cached = closure_cache.pop(required, None)
            if cached is None:
                cached = _ordered_closure(required, actions)
                if len(closure_cache) >= MAX_CLOSURE_CACHE:
                    closure_cache.popitem(last=False)
            closure_cache[required] = cached
            ordered, problem_counts, problems = cached
            if problem_counts:
                rejected += 1
                diagnostics.merge(problem_counts, problems, combination=attempted)
                continue
            steps_key = tuple(ordered)
            if steps_key in known_steps:
                duplicates += 1
                diagnostics.add("duplicate_action_plan", combination=attempted)
                continue
            # Bind every input declaration and the planner contract/version so
            # even recipe-only changes invalidate downstream selection digests.
            cid = "recipe-" + _digest({"input_digest": input_digest, "recipes": list(selection),
                                        "planning_version": PLANNING_VERSION})[:56]
            candidate = {"id": cid, "steps": ordered, "goals": deepcopy(declared_goals)}
            comparison["candidates"].append(candidate)
            if _json_size(comparison) > MAX_INPUT_BYTES:
                comparison["candidates"].pop()
                diagnostics.add("comparison_request_size_limit", combination=attempted)
                truncation_reason = "comparison_request_size"
                break
            known_steps.add(steps_key)
            candidate_recipes[cid] = list(selection)

    if candidate_recipes:
        # This is structural validation only; required unknown costs still
        # belong to rank_plans and must not suppress recipe candidates.
        _validate(comparison)
    return {
        "schema": RESULT_SCHEMA,
        "status": "candidates_built" if candidate_recipes else "no_candidates",
        "input_digest": input_digest,
        "comparison_request": comparison if candidate_recipes else None,
        "candidate_recipes": candidate_recipes,
        "diagnostics": diagnostics.items,
        "reason_counts": dict(sorted(diagnostics.counts.items())),
        "diagnostics_omitted": diagnostics.total - len(diagnostics.items),
        "diagnostics_truncated": diagnostics.total > len(diagnostics.items),
        "search": {"attempted": attempted, "candidate_count": len(candidate_recipes),
                   "rejected_combinations": rejected, "duplicate_combinations": duplicates,
                   "complete": truncation_reason is None, "truncation_reason": truncation_reason,
                   "limits": {"max_candidates": max_candidates, "max_expansions": max_expansions}},
        "planning_model": "serial_declared_recipes",
        "planning_version": PLANNING_VERSION,
        "claim": {"source_verified": False, "goal_coverage_verified": False,
                  "universal_optimality": False, "global_feasibility_verified": False},
        "boundaries": {"models": False, "network": False, "execution": False,
                       "collection": False, "storage": False},
    }
