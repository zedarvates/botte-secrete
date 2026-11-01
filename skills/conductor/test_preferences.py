"""Behavioural contracts for ranking declared serial multi-project plans."""

from __future__ import annotations

import json
import unittest
from copy import deepcopy
from decimal import ROUND_UP, localcontext
from pathlib import Path

from skills.conductor.preferences import (
    MAX_INPUT_BYTES, MAX_REASONS_PER_CANDIDATE, METRICS, REQUEST_SCHEMA,
    PROPOSAL_RESULT_SCHEMA, parse_request_json, propose_plans, rank_plans,
)


def _action(aid, projects, *, needs=(), elapsed=1, money=0, tokens=0,
            human=1, energy=1, ram=1):
    return {"id": aid, "needs": list(needs), "projects": list(projects),
            "metrics": {"elapsed_minutes": elapsed, "human_minutes": human,
                        "money": money, "tokens": tokens, "energy_wh": energy,
                        "peak_ram_gib": ram},
            "provenance": {"kind": "estimate", "ref": "synthetic-test-fixture"}}


def _request():
    return {
        "schema": REQUEST_SCHEMA, "currency": "EUR",
        "projects": [{"id": "demo", "goals": ["playable"]},
                     {"id": "plugin", "goals": ["validated"]}],
        "actions": [
            _action("shared", ["demo", "plugin"], elapsed=2, money=1, tokens=10),
            _action("fast-demo", ["demo"], needs=["shared"], elapsed=3, money=5, tokens=100),
            _action("fast-plugin", ["plugin"], needs=["shared"], elapsed=4, money=5, tokens=100),
            _action("cheap-demo", ["demo"], needs=["shared"], elapsed=10, money=0, tokens=0),
            _action("cheap-plugin", ["plugin"], needs=["shared"], elapsed=20, money=0, tokens=0),
        ],
        "candidates": [
            {"id": "rapid", "steps": ["shared", "fast-demo", "fast-plugin"],
             "goals": {"demo": ["playable"], "plugin": ["validated"]}},
            {"id": "economical", "steps": ["shared", "cheap-demo", "cheap-plugin"],
             "goals": {"demo": ["playable"], "plugin": ["validated"]}},
        ],
        "preferences": {"priorities": [{"metric": "elapsed_minutes"}, {"metric": "money"}]},
    }


def _candidate(result, cid):
    return next(item for item in result["candidates"] if item["id"] == cid)


class PlanPreferencesTests(unittest.TestCase):
    def test_user_priority_changes_winner_and_preserves_tradeoff(self):
        request = _request()
        result = rank_plans(request)
        self.assertEqual(result["winner"], "rapid")
        self.assertEqual(result["pareto_frontier"], ["economical", "rapid"])
        request["preferences"]["priorities"].reverse()
        self.assertEqual(rank_plans(request)["winner"], "economical")

    def test_hard_budget_cannot_be_outweighed_by_speed(self):
        request = _request()
        request["preferences"]["limits"] = {"money": 3}
        result = rank_plans(request)
        self.assertEqual(result["winner"], "economical")
        self.assertEqual(_candidate(result, "rapid")["status"], "rejected")

    def test_shared_action_counted_once_globally_full_cost_per_project(self):
        result = rank_plans(_request())
        rapid = _candidate(result, "rapid")
        self.assertEqual(rapid["totals"]["money"], 11)
        self.assertEqual(rapid["totals"]["tokens"], 210)
        self.assertEqual(rapid["project_totals"]["demo"]["money"], 6)
        self.assertEqual(rapid["project_totals"]["plugin"]["money"], 6)
        self.assertEqual(rapid["shared_actions"], ["shared"])
        self.assertIn("not_additive", result["project_cost_allocation"])

    def test_project_deadline_includes_prior_other_project_work(self):
        request = _request()
        request["preferences"]["project_limits"] = {"plugin": {"elapsed_minutes": 8}}
        result = rank_plans(request)
        self.assertEqual(_candidate(result, "rapid")["project_totals"]["plugin"]["elapsed_minutes"], 9)
        self.assertEqual(result["status"], "no_eligible_plan")
        self.assertIsNone(result["winner"])

    def test_project_priority_can_change_serial_order(self):
        request = _request()
        request["candidates"].append({
            "id": "plugin-first", "steps": ["shared", "fast-plugin", "fast-demo"],
            "goals": {"demo": ["playable"], "plugin": ["validated"]}})
        request["preferences"]["priorities"] = [{"project": "plugin", "metric": "elapsed_minutes"}]
        result = rank_plans(request)
        self.assertEqual(result["winner"], "plugin-first")
        self.assertEqual(_candidate(result, "plugin-first")["project_totals"]["plugin"]["elapsed_minutes"], 6)

    def test_serial_ram_is_maximum_and_energy_is_sum(self):
        request = _request()
        request["actions"][0]["metrics"]["peak_ram_gib"] = 3
        request["actions"][1]["metrics"]["peak_ram_gib"] = 7
        rapid = _candidate(rank_plans(request), "rapid")
        self.assertEqual(rapid["totals"]["peak_ram_gib"], 7)
        self.assertEqual(rapid["totals"]["energy_wh"], 3)

    def test_unknown_priority_cost_is_undetermined_not_zero(self):
        request = _request()
        request["actions"][1]["metrics"]["elapsed_minutes"] = None
        result = rank_plans(request)
        self.assertEqual(result["winner"], "economical")
        self.assertEqual(result["remaining_unknown_candidates"], ["rapid"])
        self.assertEqual(result["optimality_scope"], "known_eligible_candidates_only")
        rapid = _candidate(result, "rapid")
        self.assertEqual(rapid["status"], "undetermined")
        self.assertIsNone(rapid["totals"]["elapsed_minutes"])
        self.assertTrue(any(reason["code"] == "required_cost_unknown" for reason in rapid["reasons"]))

    def test_unknown_limit_cost_is_undetermined(self):
        request = _request()
        request["preferences"]["limits"] = {"energy_wh": 100}
        request["actions"][0]["metrics"]["energy_wh"] = None
        result = rank_plans(request)
        self.assertEqual(result["status"], "undetermined")
        self.assertIsNone(result["winner"])

    def test_unknown_irrelevant_cost_remains_visible_without_blocking(self):
        request = _request()
        request["actions"][1]["metrics"]["energy_wh"] = None
        result = rank_plans(request)
        rapid = _candidate(result, "rapid")
        self.assertEqual(result["winner"], "rapid")
        self.assertEqual(rapid["status"], "eligible")
        self.assertIn({"metric": "energy_wh"}, rapid["unknown_metrics"])

    def test_unknown_other_project_duration_can_block_project_deadline(self):
        request = _request()
        request["actions"][1]["metrics"]["elapsed_minutes"] = None
        request["preferences"]["priorities"] = [{"metric": "money"}]
        request["preferences"]["project_limits"] = {"plugin": {"elapsed_minutes": 100}}
        self.assertEqual(_candidate(rank_plans(request), "rapid")["status"], "undetermined")

    def test_known_hard_limit_failure_remains_rejected_with_unknown_cost(self):
        request = _request()
        request["actions"][1]["metrics"]["elapsed_minutes"] = None
        request["preferences"]["limits"] = {"money": 3}
        self.assertEqual(_candidate(rank_plans(request), "rapid")["status"], "rejected")

    def test_incomplete_goal_declaration_rejected(self):
        request = _request()
        request["candidates"][0]["goals"].pop("plugin")
        rapid = _candidate(rank_plans(request), "rapid")
        self.assertEqual(rapid["status"], "rejected")
        self.assertTrue(any(reason["code"] == "goals_not_declared" for reason in rapid["reasons"]))

    def test_goal_claim_without_project_action_rejected(self):
        request = _request()
        request["candidates"][0]["steps"] = ["fast-demo"]
        self.assertEqual(_candidate(rank_plans(request), "rapid")["status"], "rejected")
        reasons = _candidate(rank_plans(request), "rapid")["reasons"]
        self.assertTrue(any(reason["code"] == "project_has_no_action" for reason in reasons))

    def test_missing_dependency_rejected(self):
        request = _request()
        request["actions"][1]["needs"] = ["unavailable"]
        self.assertEqual(_candidate(rank_plans(request), "rapid")["status"], "rejected")

    def test_dependency_after_consumer_rejected(self):
        request = _request()
        request["candidates"][0]["steps"] = ["fast-demo", "shared", "fast-plugin"]
        self.assertEqual(_candidate(rank_plans(request), "rapid")["status"], "rejected")

    def test_dependency_cycle_rejected(self):
        request = _request()
        request["actions"][0]["needs"] = ["fast-demo"]
        self.assertEqual(rank_plans(request)["status"], "no_eligible_plan")

    def test_unknown_action_is_candidate_rejection(self):
        request = _request()
        request["candidates"][0]["steps"].append("missing-action")
        self.assertEqual(_candidate(rank_plans(request), "rapid")["status"], "rejected")

    def test_duplicate_actions_and_repeated_steps_are_contract_errors(self):
        request = _request()
        request["actions"].append(deepcopy(request["actions"][0]))
        with self.assertRaises(ValueError):
            rank_plans(request)
        request = _request()
        request["candidates"][0]["steps"].append("shared")
        with self.assertRaises(ValueError):
            rank_plans(request)

    def test_tie_breaking_is_stable_id_and_equal_plans_not_dominated(self):
        request = _request()
        request["candidates"] = [request["candidates"][0], deepcopy(request["candidates"][0])]
        request["candidates"][1]["id"] = "aaa"
        result = rank_plans(request)
        self.assertEqual(result["ranking"], ["aaa", "rapid"])
        self.assertEqual(result["pareto_frontier"], ["aaa", "rapid"])

    def test_dominated_plan_excluded_from_frontier(self):
        request = _request()
        request["preferences"]["priorities"] = [{"metric": "elapsed_minutes"}]
        self.assertEqual(rank_plans(request)["pareto_frontier"], ["rapid"])

    def test_input_not_mutated_and_catalogue_order_irrelevant(self):
        request = _request()
        before = deepcopy(request)
        expected = rank_plans(request)
        self.assertEqual(request, before)
        request["actions"].reverse()
        request["projects"].reverse()
        request["candidates"].reverse()
        request["actions"][-1]["projects"].reverse()
        self.assertEqual(rank_plans(request), expected)

    def test_digest_changes_for_priority_or_step_order(self):
        request = _request()
        digest = rank_plans(request)["input_digest"]
        request["preferences"]["priorities"].reverse()
        self.assertNotEqual(rank_plans(request)["input_digest"], digest)
        request = _request()
        request["candidates"][0]["steps"] = ["shared", "fast-plugin", "fast-demo"]
        self.assertNotEqual(rank_plans(request)["input_digest"], digest)

    def test_decimal_budget_does_not_reject_point_one_plus_point_two(self):
        request = _request()
        request["actions"][0]["metrics"]["money"] = 0.1
        request["actions"][1]["metrics"]["money"] = 0.2
        request["actions"][2]["metrics"]["money"] = 0
        request["preferences"]["limits"] = {"money": 0.3}
        self.assertEqual(_candidate(rank_plans(request), "rapid")["status"], "eligible")

    def test_ranking_ignores_external_decimal_precision_and_rounding(self):
        request = _request()
        request["actions"][0]["metrics"]["money"] = 0.123456
        expected = rank_plans(request)
        with localcontext() as context:
            context.prec = 2
            context.rounding = ROUND_UP
            context.Emax = 1
            self.assertEqual(rank_plans(request), expected)

    def test_unknown_keys_invalid_references_and_bad_numbers_rejected(self):
        mutations = [
            lambda r: r.update({"execute": True}),
            lambda r: r["actions"][0]["metrics"].update({"money": True}),
            lambda r: r["actions"][0]["metrics"].update({"money": -1}),
            lambda r: r["actions"][0]["metrics"].update({"money": float("nan")}),
            lambda r: r["actions"][0]["metrics"].update({"money": float("inf")}),
            lambda r: r["preferences"]["priorities"][0].update({"project": "absent"}),
            lambda r: r["preferences"]["priorities"][0].update({"project": []}),
            lambda r: r["preferences"]["priorities"][0].update({"project": {}}),
            lambda r: r["preferences"]["priorities"][0].update({"metric": []}),
            lambda r: r["actions"][0]["metrics"].update({"money": 10 ** 1000}),
            lambda r: r["projects"][0].update({"id": "unsafe id"}),
            lambda r: r["candidates"][0]["goals"].update({"demo": ["invented"]}),
            lambda r: r["actions"][0]["metrics"].pop(METRICS[0]),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                request = _request()
                mutate(request)
                with self.assertRaises(ValueError):
                    rank_plans(request)

    def test_collection_and_size_bounds_rejected(self):
        request = _request()
        request["candidates"] = [deepcopy(request["candidates"][0]) for _ in range(65)]
        with self.assertRaises(ValueError):
            rank_plans(request)
        with self.assertRaises(ValueError):
            parse_request_json(" " * (MAX_INPUT_BYTES + 1))

    def test_strict_json_rejects_duplicate_keys_constants_and_overflow(self):
        for raw in ['{"schema":1,"schema":2}', '{"x":{"a":1,"a":2}}',
                    '{"x":NaN}', '{"x":Infinity}', '{"x":-Infinity}',
                    '{"x":1e999}', '[]', '{broken']:
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    parse_request_json(raw)

    def test_deep_json_and_non_json_direct_input_raise_value_error(self):
        with self.assertRaises(ValueError):
            parse_request_json('{"x":' + '[' * 1500 + '0' + ']' * 1500 + '}')
        with self.assertRaises(ValueError):
            rank_plans({"schema": object()})

    def test_provenance_and_goal_claims_are_not_promoted_to_verification(self):
        request = _request()
        request["actions"][0]["provenance"]["kind"] = "measurement"
        result = rank_plans(request)
        self.assertFalse(result["claim"]["source_verified"])
        self.assertFalse(result["claim"]["goal_coverage_verified"])
        self.assertIsNone(result["claim"]["measured_gain"])
        self.assertTrue(all(value is False for value in result["boundaries"].values()))
        self.assertEqual(_candidate(result, "rapid")["goal_coverage"], "declared_unverified")
        json.dumps(result, allow_nan=False)

    def test_dense_maximum_request_retains_bounded_reasons_and_exact_counts(self):
        action_ids = [f"a{index:03}" for index in range(256)]
        request = {
            "schema": REQUEST_SCHEMA, "currency": "EUR",
            "projects": [{"id": "p", "goals": ["done"]}],
            "actions": [_action(aid, ["p"], needs=action_ids) for aid in action_ids],
            "candidates": [{"id": f"c{index:02}", "steps": action_ids[:],
                            "goals": {"p": ["done"]}} for index in range(64)],
            "preferences": {"priorities": [{"metric": "elapsed_minutes"}]},
        }
        self.assertLess(len(json.dumps(request).encode("utf-8")), MAX_INPUT_BYTES)
        result = rank_plans(request)
        self.assertLess(len(json.dumps(result).encode("utf-8")), 2 * MAX_INPUT_BYTES)
        expected = 256 * 257 // 2
        for candidate in result["candidates"]:
            self.assertEqual(candidate["status"], "rejected")
            self.assertEqual(len(candidate["reasons"]), MAX_REASONS_PER_CANDIDATE)
            self.assertEqual(candidate["reason_counts"], {"dependency_not_preceding": expected})
            self.assertEqual(candidate["reasons_omitted"], expected - MAX_REASONS_PER_CANDIDATE)
            self.assertTrue(candidate["reasons_truncated"])
        request["actions"].reverse()
        request["actions"][0]["needs"].reverse()
        self.assertEqual(rank_plans(request), result)

    def test_omitted_unknown_action_still_invalidates_totals_and_counts_unknowns(self):
        action_ids = [f"a{index:03}" for index in range(70)]
        request = {
            "schema": REQUEST_SCHEMA, "currency": "EUR",
            "projects": [{"id": "p", "goals": ["done"]}],
            "actions": [_action(aid, ["p"], needs=action_ids) for aid in action_ids],
            "candidates": [{"id": "candidate", "steps": action_ids + ["missing"],
                            "goals": {"p": ["done"]}}],
            "preferences": {"priorities": [{"metric": "elapsed_minutes"}, {"metric": "money"}]},
        }
        candidate = rank_plans(request)["candidates"][0]
        self.assertEqual(candidate["status"], "rejected")
        self.assertTrue(all(value is None for value in candidate["totals"].values()))
        self.assertTrue(all(value is None for value in candidate["project_totals"]["p"].values()))
        self.assertNotIn("unknown_action", [reason["code"] for reason in candidate["reasons"]])
        self.assertEqual(candidate["reason_counts"], {
            "dependency_not_preceding": 70 * 71 // 2,
            "required_cost_unknown": 2, "unknown_action": 1,
        })
        self.assertEqual(candidate["reasons_omitted"], 70 * 71 // 2 + 3 - MAX_REASONS_PER_CANDIDATE)

    def test_omitted_unknown_cost_reasons_preserve_undetermined_status(self):
        project_ids = [f"p{index:02}" for index in range(32)]
        action = _action("shared", project_ids)
        action["metrics"] = {metric: None for metric in METRICS}
        request = {
            "schema": REQUEST_SCHEMA, "currency": "EUR",
            "projects": [{"id": pid, "goals": ["done"]} for pid in project_ids],
            "actions": [action],
            "candidates": [{"id": "candidate", "steps": ["shared"],
                            "goals": {pid: ["done"] for pid in project_ids}}],
            "preferences": {
                "priorities": [{"metric": "elapsed_minutes"}],
                "project_limits": {pid: {metric: 100 for metric in METRICS} for pid in project_ids},
            },
        }
        result = rank_plans(request)
        candidate = result["candidates"][0]
        self.assertEqual(result["status"], "undetermined")
        self.assertIsNone(result["winner"])
        self.assertEqual(candidate["status"], "undetermined")
        self.assertEqual(candidate["reason_counts"], {"required_cost_unknown": 193})
        self.assertEqual(candidate["reasons_omitted"], 193 - MAX_REASONS_PER_CANDIDATE)
        self.assertEqual(len(candidate["unknown_metrics"]), 198)

    def test_shipped_example_is_valid_and_switches_with_urgency(self):
        path = Path(__file__).resolve().parents[2] / "examples" / "parcimonia_plan_preferences.json"
        request = parse_request_json(path.read_text(encoding="utf-8"))
        self.assertEqual(rank_plans(request)["winner"], "economical")
        request["preferences"]["priorities"] = [{"metric": "elapsed_minutes"}, {"metric": "money"}]
        self.assertEqual(rank_plans(request)["winner"], "rapid")


class PlanProposalTests(unittest.TestCase):
    def test_two_options_expose_steps_costs_and_advisory_recommendation(self):
        request = _request()
        ranking = rank_plans(request)
        result = propose_plans(request)
        self.assertEqual(result["schema"], PROPOSAL_RESULT_SCHEMA)
        self.assertEqual(result["status"], "proposed")
        self.assertEqual(result["recommended_candidate_id"], "rapid")
        self.assertIsNone(result["selected_candidate_id"])
        self.assertEqual(result["selection_status"], "not_selected")
        self.assertEqual([option["candidate_id"] for option in result["options"]],
                         ["rapid", "economical"])
        self.assertEqual([option["rank"] for option in result["options"]], [1, 2])
        self.assertEqual([option["recommended"] for option in result["options"]],
                         [True, False])
        for option in result["options"]:
            candidate = next(candidate for candidate in request["candidates"]
                             if candidate["id"] == option["candidate_id"])
            self.assertEqual(option["steps"], candidate["steps"])
            report = _candidate(ranking, option["candidate_id"])
            for key in ("totals", "project_totals", "unknown_metrics", "shared_actions",
                        "goal_coverage"):
                self.assertEqual(option[key], report[key])
        self.assertEqual(result["unavailable_candidates"], [])
        for key in ("input_digest", "currency", "priorities", "method", "planning_model",
                    "optimality_scope", "claim", "boundaries"):
            self.assertEqual(result[key], ranking[key])
        self.assertTrue(all(value is False for value in result["boundaries"].values()))
        json.dumps(result, allow_nan=False)

    def test_sole_option_remains_unselected(self):
        request = _request()
        request["candidates"] = request["candidates"][:1]
        result = propose_plans(request)
        self.assertEqual(len(result["options"]), 1)
        self.assertEqual(result["recommended_candidate_id"], "rapid")
        self.assertIsNone(result["selected_candidate_id"])
        self.assertEqual(result["selection_status"], "not_selected")

    def test_equal_options_have_stable_order_without_user_selection(self):
        request = _request()
        request["candidates"] = [request["candidates"][0], deepcopy(request["candidates"][0])]
        request["candidates"][1]["id"] = "aaa"
        result = propose_plans(request)
        self.assertEqual([option["candidate_id"] for option in result["options"]],
                         ["aaa", "rapid"])
        self.assertTrue(all(option["pareto"] for option in result["options"]))
        self.assertEqual(result["recommended_candidate_id"], "aaa")
        self.assertIsNone(result["selected_candidate_id"])

    def test_dominated_nonrecommended_candidate_remains_an_option(self):
        request = _request()
        request["preferences"]["priorities"] = [{"metric": "elapsed_minutes"}]
        result = propose_plans(request)
        self.assertEqual(len(result["options"]), 2)
        alternative = result["options"][1]
        self.assertEqual(alternative["candidate_id"], "economical")
        self.assertEqual(alternative["rank"], 2)
        self.assertFalse(alternative["recommended"])
        self.assertFalse(alternative["pareto"])
        self.assertTrue(result["options"][0]["pareto"])

    def test_unknown_and_rejected_candidates_keep_reasons_outside_options(self):
        request = _request()
        request["actions"][1]["metrics"]["elapsed_minutes"] = None
        rejected = deepcopy(request["candidates"][1])
        rejected["id"] = "incomplete"
        rejected["goals"].pop("plugin")
        request["candidates"].append(rejected)
        ranking = rank_plans(request)
        result = propose_plans(request)
        self.assertEqual([option["candidate_id"] for option in result["options"]],
                         ["economical"])
        self.assertEqual(result["unavailable_candidates"],
                         [_candidate(ranking, "incomplete"), _candidate(ranking, "rapid")])
        self.assertEqual([report["status"] for report in result["unavailable_candidates"]],
                         ["rejected", "undetermined"])
        self.assertTrue(all(report["reasons"] for report in result["unavailable_candidates"]))

    def test_no_eligible_option_preserves_unknown_or_rejected_status(self):
        for expected_status in ("undetermined", "no_eligible_plan"):
            with self.subTest(status=expected_status):
                request = _request()
                if expected_status == "undetermined":
                    request["actions"][0]["metrics"]["elapsed_minutes"] = None
                else:
                    request["preferences"]["limits"] = {"money": 0}
                result = propose_plans(request)
                self.assertEqual(result["status"], expected_status)
                self.assertEqual(result["options"], [])
                self.assertEqual(len(result["unavailable_candidates"]), 2)
                self.assertIsNone(result["recommended_candidate_id"])
                self.assertIsNone(result["selected_candidate_id"])
                self.assertEqual(result["selection_status"], "not_selected")

    def test_proposal_preserves_input_and_ignores_catalogue_order(self):
        request = _request()
        before = deepcopy(request)
        expected = propose_plans(request)
        self.assertEqual(request, before)
        request["actions"].reverse()
        request["projects"].reverse()
        request["candidates"].reverse()
        request["actions"][-1]["projects"].reverse()
        self.assertEqual(propose_plans(request), expected)
        expected["options"][0]["steps"].append("output-only-change")
        self.assertEqual(request["candidates"][1]["steps"],
                         before["candidates"][0]["steps"])

    def test_preference_change_recommends_another_option_without_selecting(self):
        request = _request()
        first = propose_plans(request)
        request["preferences"]["priorities"].reverse()
        second = propose_plans(request)
        self.assertEqual(first["recommended_candidate_id"], "rapid")
        self.assertEqual(second["recommended_candidate_id"], "economical")
        self.assertEqual({option["candidate_id"] for option in first["options"]},
                         {option["candidate_id"] for option in second["options"]})
        self.assertNotEqual(first["input_digest"], second["input_digest"])
        self.assertIsNone(first["selected_candidate_id"])
        self.assertIsNone(second["selected_candidate_id"])


if __name__ == "__main__":
    unittest.main()
