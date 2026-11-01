"""Contracts for deterministic candidate construction from declared recipes."""

from __future__ import annotations

import json
import unittest
from collections import OrderedDict
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from skills.conductor import recipes as recipe_module
from skills.conductor.handoff import prepare_plan_handoff
from skills.conductor.preferences import METRICS, propose_plans, rank_plans
from skills.conductor.recipes import (
    MAX_CLOSURE_CACHE, MAX_DIAGNOSTICS, MAX_INPUT_BYTES, REQUEST_SCHEMA, RESULT_SCHEMA,
    build_plan_candidates, parse_request_json,
)
from skills.conductor.selection import select_plan


def _action(aid, projects=("demo",), needs=(), cost=1):
    return {"id": aid, "projects": list(projects), "needs": list(needs),
            "metrics": {metric: cost for metric in METRICS},
            "provenance": {"kind": "estimate", "ref": "synthetic-fixture-v1"}}


def _request():
    return {
        "schema": REQUEST_SCHEMA, "currency": "EUR",
        "projects": [{"id": "demo", "goals": ["playable"]},
                     {"id": "plugin", "goals": ["validated"]}],
        "actions": [
            _action("shared", ("demo", "plugin"), cost=2),
            _action("fast-demo", needs=("shared",)),
            _action("cheap-demo", needs=("shared",), cost=0),
            _action("fast-plugin", ("plugin",), ("shared",)),
            _action("cheap-plugin", ("plugin",), ("shared",), cost=0),
        ],
        "recipes": [
            {"id": "demo-fast", "project": "demo", "goal": "playable", "actions": ["fast-demo"]},
            {"id": "demo-cheap", "project": "demo", "goal": "playable", "actions": ["cheap-demo"]},
            {"id": "plugin-fast", "project": "plugin", "goal": "validated", "actions": ["fast-plugin"]},
            {"id": "plugin-cheap", "project": "plugin", "goal": "validated", "actions": ["cheap-plugin"]},
        ],
        "preferences": {"priorities": [{"metric": "money"}, {"metric": "elapsed_minutes"}]},
    }


def _single():
    return {"schema": REQUEST_SCHEMA, "currency": "EUR",
            "projects": [{"id": "demo", "goals": ["done"]}],
            "actions": [_action("finish")],
            "recipes": [{"id": "method", "project": "demo", "goal": "done", "actions": ["finish"]}],
            "preferences": {"priorities": [{"metric": "elapsed_minutes"}]}}


class RecipePlanningTests(unittest.TestCase):
    def test_two_methods_for_each_of_two_goals_builds_four_candidates(self):
        result = build_plan_candidates(_request())
        self.assertEqual(result["schema"], RESULT_SCHEMA)
        self.assertEqual(result["status"], "candidates_built")
        self.assertEqual(result["search"]["attempted"], 4)
        self.assertEqual(result["search"]["candidate_count"], 4)
        self.assertTrue(result["search"]["complete"])
        self.assertIsNone(result["search"]["truncation_reason"])
        self.assertEqual(list(result["candidate_recipes"].values()), [
            ["demo-cheap", "plugin-cheap"], ["demo-cheap", "plugin-fast"],
            ["demo-fast", "plugin-cheap"], ["demo-fast", "plugin-fast"]])
        self.assertEqual(rank_plans(result["comparison_request"])["status"], "ranked")

    def test_shared_transitive_closure_is_included_and_charged_once(self):
        request = _request()
        # Dependency beneficiaries may differ from a goal's recipe project.
        request["actions"].append(_action("foundation", ("plugin",), cost=3))
        request["actions"][0]["needs"] = ["foundation"]
        result = build_plan_candidates(request)
        for candidate in result["comparison_request"]["candidates"]:
            self.assertEqual(candidate["steps"].count("foundation"), 1)
            self.assertEqual(candidate["steps"].count("shared"), 1)
            self.assertEqual(candidate["steps"][:2], ["foundation", "shared"])
        ranking = rank_plans(result["comparison_request"])
        self.assertEqual(next(item for item in ranking["candidates"]
                              if item["id"] == ranking["winner"])["totals"]["money"], 5)

    def test_backward_dependencies_are_topologically_ordered(self):
        request = _single()
        request["actions"] = [_action("a-finish", needs=("z-prepare",)),
                              _action("z-prepare", needs=("middle",)), _action("middle")]
        request["recipes"][0]["actions"] = ["a-finish"]
        steps = build_plan_candidates(request)["comparison_request"]["candidates"][0]["steps"]
        self.assertEqual(steps, ["middle", "z-prepare", "a-finish"])

    def test_cycle_rejects_only_reached_combination_without_global_claim(self):
        request = _request()
        request["actions"][1]["needs"] = ["fast-demo"]
        result = build_plan_candidates(request)
        self.assertEqual(result["search"]["candidate_count"], 2)
        self.assertEqual(result["search"]["rejected_combinations"], 2)
        self.assertEqual(result["reason_counts"], {"dependency_cycle": 2})
        self.assertTrue(result["search"]["complete"])
        self.assertIs(result["claim"]["global_feasibility_verified"], False)

    def test_missing_dependency_is_diagnosed_without_inventing_action(self):
        request = _single()
        request["actions"][0]["needs"] = ["absent"]
        result = build_plan_candidates(request)
        self.assertEqual(result["status"], "no_candidates")
        self.assertIsNone(result["comparison_request"])
        self.assertEqual(result["diagnostics"], [{"code": "missing_dependency", "combination": 1,
                                                  "action": "finish", "dependency": "absent"}])
        self.assertEqual(result["search"]["rejected_combinations"], 1)

    def test_unreached_catalogue_cycles_and_missing_dependencies_do_not_block(self):
        request = _single()
        request["actions"].extend([_action("cycle", needs=("cycle",)),
                                   _action("unused", needs=("absent",))])
        result = build_plan_candidates(request)
        self.assertEqual(result["diagnostics"], [])
        self.assertEqual(result["comparison_request"]["candidates"][0]["steps"], ["finish"])

    def test_missing_recipe_is_explicit_without_partial_goal_candidates(self):
        request = _request()
        request["recipes"] = [recipe for recipe in request["recipes"] if recipe["project"] == "demo"]
        result = build_plan_candidates(request)
        self.assertEqual(result["status"], "no_candidates")
        self.assertEqual(result["diagnostics"], [{"code": "missing_recipe", "project": "plugin", "goal": "validated"}])
        self.assertEqual(result["search"]["attempted"], 0)
        self.assertTrue(result["search"]["complete"])
        request["recipes"] = []
        self.assertEqual(build_plan_candidates(request)["reason_counts"], {"missing_recipe": 2})

    def test_candidate_limit_is_explicit_and_exact_final_limit_is_complete(self):
        request = _request()
        request["max_candidates"] = 2
        result = build_plan_candidates(request)
        self.assertEqual(result["search"]["candidate_count"], 2)
        self.assertEqual(result["search"]["attempted"], 2)
        self.assertFalse(result["search"]["complete"])
        self.assertEqual(result["search"]["truncation_reason"], "max_candidates")
        request["max_candidates"] = 4
        request["max_expansions"] = 4
        self.assertTrue(build_plan_candidates(request)["search"]["complete"])
        request = _single()
        request["max_candidates"] = 1
        request["recipes"].append({**request["recipes"][0], "id": "method-copy"})
        result = build_plan_candidates(request)
        self.assertFalse(result["search"]["complete"])
        self.assertEqual(result["search"]["attempted"], 1)

    def test_duplicate_combinations_consume_expansion_budget(self):
        request = _single()
        request["recipes"].extend({**request["recipes"][0], "id": f"method-{index}"} for index in range(8))
        request["max_expansions"] = 3
        result = build_plan_candidates(request)
        self.assertEqual(result["search"]["candidate_count"], 1)
        self.assertEqual(result["search"]["attempted"], 3)
        self.assertEqual(result["search"]["duplicate_combinations"], 2)
        self.assertEqual(result["reason_counts"], {"duplicate_action_plan": 2})
        self.assertFalse(result["search"]["complete"])
        self.assertEqual(result["search"]["truncation_reason"], "max_expansions")
        request["max_expansions"] = 9
        self.assertTrue(build_plan_candidates(request)["search"]["complete"])

    def test_rejected_combinations_consume_budget_and_diagnostics_are_bounded(self):
        request = _single()
        request["actions"][0]["needs"] = ["absent"]
        request["recipes"] = [{**request["recipes"][0], "id": f"method-{index:03}"}
                              for index in range(MAX_DIAGNOSTICS + 4)]
        request["max_expansions"] = MAX_DIAGNOSTICS + 2
        result = build_plan_candidates(request)
        self.assertEqual(result["search"]["attempted"], MAX_DIAGNOSTICS + 2)
        self.assertEqual(result["search"]["candidate_count"], 0)
        self.assertFalse(result["search"]["complete"])
        self.assertEqual(result["reason_counts"], {"missing_dependency": MAX_DIAGNOSTICS + 2})
        self.assertEqual(len(result["diagnostics"]), MAX_DIAGNOSTICS)
        self.assertEqual(result["diagnostics_omitted"], 2)
        self.assertTrue(result["diagnostics_truncated"])

    def test_repeated_dense_invalid_graph_computes_closure_once_with_exact_counts(self):
        request = _single()
        request["projects"][0]["goals"] = ["one", "two"]
        absent = [f"m{index:03}" for index in range(256)]
        request["actions"] = [_action(f"a{index:03}", needs=absent) for index in range(256)]
        required = [action["id"] for action in request["actions"]]
        request["recipes"] = [
            {"id": f"{goal}-{index:03}", "project": "demo", "goal": goal, "actions": required[:]}
            for goal in ("one", "two") for index in range(64)]
        request["max_expansions"] = 4096
        self.assertLess(len(json.dumps(request, ensure_ascii=False).encode("utf-8")), MAX_INPUT_BYTES)
        original = recipe_module._ordered_closure

        def bounded_closure(*args):
            value = original(*args)
            self.assertEqual(value[1], {"missing_dependency": 65536})
            self.assertEqual(len(value[2]), MAX_DIAGNOSTICS)
            return value

        with patch.object(recipe_module, "_ordered_closure", side_effect=bounded_closure) as closure:
            result = build_plan_candidates(request)
        self.assertEqual(closure.call_count, 1)
        self.assertEqual(result["search"]["attempted"], 4096)
        self.assertEqual(result["search"]["rejected_combinations"], 4096)
        self.assertEqual(result["search"]["duplicate_combinations"], 0)
        self.assertEqual(result["search"]["candidate_count"], 0)
        self.assertTrue(result["search"]["complete"])
        self.assertEqual(result["reason_counts"], {"missing_dependency": 65536 * 4096})
        self.assertEqual(result["diagnostics_omitted"], 65536 * 4096 - MAX_DIAGNOSTICS)
        self.assertEqual(len(result["diagnostics"]), MAX_DIAGNOSTICS)
        self.assertEqual({item["combination"] for item in result["diagnostics"]}, {1})
        self.assertEqual(result["diagnostics"][0]["dependency"], "m000")
        self.assertEqual(result["diagnostics"][-1]["dependency"], "m063")
        self.assertLess(len(json.dumps(result, ensure_ascii=False).encode("utf-8")), 20 * 1024)

    def test_closure_cache_is_bounded_lru_and_eviction_preserves_attempt_counts(self):
        request = _single()
        request["actions"] = [_action(f"a{index:03}", needs=("absent",))
                              for index in range(MAX_CLOSURE_CACHE + 1)]
        sequence = [*range(MAX_CLOSURE_CACHE), 0, MAX_CLOSURE_CACHE, 0, 1]
        request["recipes"] = [
            {"id": f"method-{index:03}", "project": "demo", "goal": "done", "actions": [f"a{aid:03}"]}
            for index, aid in enumerate(sequence)]
        request["max_expansions"] = len(sequence)
        maximum_sizes = []
        evicted = []

        class TrackingLRU(OrderedDict):
            def __setitem__(self, key, value):
                super().__setitem__(key, value)
                maximum_sizes.append(len(self))

            def popitem(self, last=True):
                item = super().popitem(last=last)
                evicted.append(item[0])
                return item

        with patch.object(recipe_module, "OrderedDict", TrackingLRU), \
                patch.object(recipe_module, "_ordered_closure", wraps=recipe_module._ordered_closure) as closure:
            result = build_plan_candidates(request)
        self.assertEqual(closure.call_count, MAX_CLOSURE_CACHE + 2)
        self.assertEqual(max(maximum_sizes), MAX_CLOSURE_CACHE)
        self.assertEqual(evicted, [frozenset({"a001"}), frozenset({"a002"})])
        self.assertEqual(result["search"]["attempted"], len(sequence))
        self.assertEqual(result["search"]["rejected_combinations"], len(sequence))
        self.assertEqual(result["reason_counts"], {"missing_dependency": len(sequence)})
        self.assertTrue(result["search"]["complete"])

    def test_closure_cache_is_per_request_and_cached_successes_still_count_duplicates(self):
        request = _single()
        request["recipes"].extend({**request["recipes"][0], "id": f"method-{index}"} for index in range(8))
        with patch.object(recipe_module, "_ordered_closure", wraps=recipe_module._ordered_closure) as closure:
            first = build_plan_candidates(request)
            self.assertEqual(closure.call_count, 1)
            request["actions"][0]["needs"] = ["new-dependency"]
            second = build_plan_candidates(request)
            self.assertEqual(closure.call_count, 2)
        self.assertEqual(first["search"]["attempted"], 9)
        self.assertEqual(first["search"]["duplicate_combinations"], 8)
        self.assertEqual(first["search"]["rejected_combinations"], 0)
        self.assertEqual(second["search"]["attempted"], 9)
        self.assertEqual(second["search"]["duplicate_combinations"], 0)
        self.assertEqual(second["search"]["rejected_combinations"], 9)
        self.assertIsNone(second["comparison_request"])
        self.assertNotEqual(first["input_digest"], second["input_digest"])

    def test_catalogue_order_has_no_effect_on_output_and_input_is_unchanged(self):
        request = _request()
        original = deepcopy(request)
        expected = build_plan_candidates(request)
        self.assertEqual(request, original)
        request["projects"].reverse()
        request["actions"].reverse()
        request["recipes"].reverse()
        for action in request["actions"]:
            action["needs"].reverse()
            action["projects"].reverse()
        self.assertEqual(build_plan_candidates(request), expected)
        expected["comparison_request"]["actions"][0]["metrics"]["money"] = 999
        self.assertEqual(original["actions"][0]["metrics"]["money"], 2)

    def test_digest_and_candidate_ids_bind_recipe_and_action_version_changes(self):
        request = _request()
        original = build_plan_candidates(request)
        for field in ("recipe", "version", "priority", "budget"):
            changed = deepcopy(request)
            if field == "recipe":
                changed["recipes"][0]["id"] += "-v2"
            elif field == "version":
                changed["actions"][0]["provenance"]["ref"] = "synthetic-fixture-v2"
            elif field == "priority":
                changed["preferences"]["priorities"].reverse()
            else:
                changed["max_expansions"] = 128
            with self.subTest(field=field):
                result = build_plan_candidates(changed)
                self.assertNotEqual(result["input_digest"], original["input_digest"])
                self.assertTrue(set(result["candidate_recipes"]).isdisjoint(original["candidate_recipes"]))

    def test_unknown_costs_still_produce_candidates_for_undetermined_ranking(self):
        request = _single()
        request["actions"][0]["metrics"]["elapsed_minutes"] = None
        result = build_plan_candidates(request)
        self.assertEqual(result["status"], "candidates_built")
        self.assertEqual(result["diagnostics"], [])
        self.assertEqual(rank_plans(result["comparison_request"])["status"], "undetermined")

    def test_generated_request_connects_to_proposals_selection_and_supplied_handoff(self):
        result = build_plan_candidates(_request())
        request = result["comparison_request"]
        proposal = propose_plans(request)
        cid = proposal["recommended_candidate_id"]
        receipt = select_plan(request, cid, proposal["input_digest"])
        actions = {action["id"]: action for action in request["actions"]}
        # Commands are independently supplied by this fixture, never generated
        # by build_plan_candidates or inferred from recipe declarations.
        plan = {"schema": "botte.skill-plan/v1", "goal": "Synthetic declared goal",
                "context": "recipe-contract-fixture", "steps": [
                    {"id": aid, "capability": "synthetic-fixture", "command": "caller-supplied-command",
                     "local": True, "needs": list(actions[aid]["needs"]), "requires": [],
                     "ensures": [], "observes": [], "source_hashes": {}}
                    for aid in receipt["selected_plan"]["steps"]]}
        handoff = prepare_plan_handoff(request, receipt, plan)
        self.assertEqual(handoff["status"], "prepared_unverified")
        self.assertFalse(handoff["execution_authorized"])
        self.assertEqual(set(receipt["selected_plan"]["steps"]),
                         set(next(candidate for candidate in request["candidates"] if candidate["id"] == cid)["steps"]))

    def test_strict_recipe_fields_identifiers_and_references(self):
        mutations = [
            lambda request: request.update(unexpected=True),
            lambda request: request.update(schema="parcimonia.recipe-planning/v2"),
            lambda request: request["recipes"][0].update(extra=True),
            lambda request: request["recipes"][0].update(id="not an identifier"),
            lambda request: request["recipes"][0].update(project="unknown"),
            lambda request: request["recipes"][0].update(goal="unknown"),
            lambda request: request["recipes"][0].update(actions=["unknown"]),
            lambda request: request["recipes"][0].update(actions=[]),
            lambda request: request["recipes"][0].update(actions=["finish", "finish"]),
            lambda request: request["recipes"].append(deepcopy(request["recipes"][0])),
        ]
        for index, mutation in enumerate(mutations):
            request = _single()
            mutation(request)
            with self.subTest(mutation=index), self.assertRaises(ValueError):
                build_plan_candidates(request)
        request = _request()
        request["recipes"][0]["actions"] = ["fast-plugin"]
        with self.assertRaisesRegex(ValueError, "does not benefit"):
            build_plan_candidates(request)

    def test_existing_project_action_and_preference_contracts_are_reused(self):
        mutations = [
            lambda request: request.update(currency="eur"),
            lambda request: request["projects"].append(deepcopy(request["projects"][0])),
            lambda request: request["projects"][0].update(goals=["done", "done"]),
            lambda request: request["actions"].append(deepcopy(request["actions"][0])),
            lambda request: request["actions"][0].update(projects=["unknown"]),
            lambda request: request["actions"][0]["metrics"].update(money=True),
            lambda request: request["actions"][0]["metrics"].update(money=float("nan")),
            lambda request: request["actions"][0]["metrics"].update(money=float("inf")),
            lambda request: request["actions"][0]["metrics"].update(money=-1),
            lambda request: request["preferences"]["priorities"][0].update(metric="unknown"),
            lambda request: request["preferences"].update(limits={"money": True}),
            lambda request: request["preferences"]["priorities"].append({"metric": "elapsed_minutes"}),
        ]
        for index, mutation in enumerate(mutations):
            request = _single()
            mutation(request)
            with self.subTest(mutation=index), self.assertRaises(ValueError):
                build_plan_candidates(request)

    def test_limits_are_bounded_integers_with_defaults(self):
        self.assertEqual(build_plan_candidates(_single())["search"]["limits"],
                         {"max_candidates": 16, "max_expansions": 256})
        for name, maximum in (("max_candidates", 64), ("max_expansions", 4096)):
            for value in (0, -1, maximum + 1, True, 1.0, None, float("nan")):
                request = _single()
                request[name] = value
                with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                    build_plan_candidates(request)
            request[name] = maximum
            self.assertEqual(build_plan_candidates(request)["search"]["limits"][name], maximum)

    def test_strict_json_parser_rejects_duplicates_nonfinite_depth_and_size(self):
        for raw in ('{"schema":"x","schema":"x"}', '{"x":NaN}', '{"x":Infinity}',
                    '{"x":1e999}', '[' + '[],' * 3 + '[]]', '{"x":' + '[' * 65 + '0' + ']' * 65 + '}',
                    '{"x":"' + 'x' * MAX_INPUT_BYTES + '"}'):
            with self.subTest(prefix=raw[:40]), self.assertRaises(ValueError):
                parse_request_json(raw)
        self.assertEqual(build_plan_candidates(parse_request_json(json.dumps(_single()))),
                         build_plan_candidates(_single()))

    def test_direct_call_bounds_json_types_depth_and_size(self):
        for invalid in (None, [], (), {1: "value"}, {"schema": object()}):
            with self.subTest(invalid=type(invalid).__name__), self.assertRaises(ValueError):
                build_plan_candidates(invalid)
        request = _single()
        request["unexpected"] = "x" * MAX_INPUT_BYTES
        with self.assertRaisesRegex(ValueError, "1 MiB"):
            build_plan_candidates(request)
        deep = []
        for _ in range(66):
            deep = [deep]
        with self.assertRaisesRegex(ValueError, "64 nesting"):
            build_plan_candidates({"deep": deep})
        # Exactly 1 MiB remains valid even when the shared validator needs an
        # artificial candidate wrapper. None of these dependencies is reached.
        request = _single()
        request["recipes"] = []
        request["actions"] = [_action(f"action-{index:03}") for index in range(64)]
        dependencies = [f"dep{index:03}" + "x" * 58 for index in range(256)]
        size = len(json.dumps(request, ensure_ascii=False).encode("utf-8"))
        for index in range((MAX_INPUT_BYTES - size - 512) // 68):
            request["actions"][index // 256]["needs"].append(dependencies[index % 256])
        remaining = MAX_INPUT_BYTES - len(json.dumps(request, ensure_ascii=False).encode("utf-8"))
        for action in request["actions"]:
            extra = min(remaining, 512 - len(action["provenance"]["ref"]))
            action["provenance"]["ref"] += "x" * extra
            remaining -= extra
        self.assertEqual(remaining, 0)
        self.assertEqual(len(json.dumps(request, ensure_ascii=False).encode("utf-8")), MAX_INPUT_BYTES)
        self.assertEqual(build_plan_candidates(request)["reason_counts"], {"missing_recipe": 1})

    def test_comparison_size_limit_keeps_output_valid_and_reports_truncation(self):
        # Use the same size function and lower only this module's output cap;
        # all emitted requests still pass the real downstream validator.
        request = _request()
        full = build_plan_candidates(request)["comparison_request"]
        limited = deepcopy(full)
        limited["candidates"] = limited["candidates"][:2]
        size = len(json.dumps(limited, allow_nan=False, ensure_ascii=False).encode("utf-8"))
        with patch("skills.conductor.recipes.MAX_INPUT_BYTES", size):
            result = build_plan_candidates(request)
        self.assertEqual(result["search"]["candidate_count"], 2)
        self.assertEqual(result["search"]["truncation_reason"], "comparison_request_size")
        self.assertFalse(result["search"]["complete"])
        self.assertEqual(rank_plans(result["comparison_request"])["status"], "ranked")

    def test_boundaries_and_declarations_do_not_claim_semantic_proof(self):
        with patch("builtins.open", side_effect=AssertionError("unexpected I/O")), \
                patch("subprocess.run", side_effect=AssertionError("unexpected execution")), \
                patch("socket.socket", side_effect=AssertionError("unexpected network")):
            result = build_plan_candidates(_single())
        self.assertTrue(all(value is False for value in result["boundaries"].values()))
        self.assertTrue(all(value is False for value in result["claim"].values()))
        candidate = result["comparison_request"]["candidates"][0]
        self.assertEqual(set(candidate), {"id", "steps", "goals"})
        self.assertNotIn("command", json.dumps(result))

    def test_example_is_valid_and_expands_to_four_alternatives(self):
        path = Path(__file__).resolve().parents[2] / "examples" / "parcimonia_recipe_planning.json"
        result = build_plan_candidates(parse_request_json(path.read_text(encoding="utf-8")))
        self.assertEqual(result["search"]["candidate_count"], 4)
        self.assertTrue(result["search"]["complete"])
        self.assertEqual(rank_plans(result["comparison_request"])["status"], "ranked")


if __name__ == "__main__":
    unittest.main()
