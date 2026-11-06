"""Contracts for bounded, advisory measurement suggestions."""

from __future__ import annotations

import json
import unittest
from copy import deepcopy
from unittest.mock import patch

from skills.conductor import measurement
from skills.conductor.measurement import MAX_UNKNOWN_CONTEXTS, RESULT_SCHEMA, suggest_plan_measurements
from skills.conductor.preferences import MAX_INPUT_BYTES, METRICS, REQUEST_SCHEMA as COMPARISON_SCHEMA
from skills.conductor.uncertainty import REQUEST_SCHEMA


def _action(aid, *, projects=("p",), money=0, elapsed=1, needs=()):
    return {"id": aid, "needs": list(needs), "projects": list(projects),
            "metrics": {"elapsed_minutes": elapsed, "human_minutes": 0,
                        "money": money, "tokens": 0, "energy_wh": 0,
                        "peak_ram_gib": 0},
            "provenance": {"kind": "estimate", "ref": "synthetic fixture"}}


def _range(aid, metric="money", lower=0, upper=10):
    return {"action_id": aid, "metric": metric, "lower": lower, "upper": upper,
            "provenance": {"kind": "estimate", "ref": "synthetic interval"}}


def _request():
    return {"schema": REQUEST_SCHEMA, "comparison_request": {
        "schema": COMPARISON_SCHEMA, "currency": "EUR",
        "projects": [{"id": "p", "goals": ["done"]}],
        "actions": [_action("a", money=1), _action("b", money=5)],
        "candidates": [{"id": aid, "steps": [aid], "goals": {"p": ["done"]}}
                       for aid in ("a", "b")],
        "preferences": {"priorities": [{"metric": "money"}]}}, "ranges": []}


class PlanMeasurementTests(unittest.TestCase):
    def test_endpoint_flip_is_advisory_and_uses_two_rank_calls(self):
        request = _request()
        request["ranges"] = [_range("a")]
        request["comparison_request"]["actions"][0]["provenance"]["kind"] = "measurement"
        with patch.object(measurement, "analyse_plan_uncertainty", wraps=measurement.analyse_plan_uncertainty) as analyser, \
                patch.object(measurement, "rank_plans", wraps=measurement.rank_plans) as ranker:
            result = suggest_plan_measurements(request)
        self.assertEqual(analyser.call_count, 1)
        self.assertEqual(ranker.call_count, 2)
        for call in ranker.call_args_list:
            projected = next(item for item in call.args[0]["actions"] if item["id"] == "a")
            self.assertEqual(projected["provenance"]["kind"], "estimate")
        self.assertEqual(request["comparison_request"]["actions"][0]["provenance"]["kind"], "measurement")
        question = result["questions"][0]
        self.assertEqual(result["schema"], RESULT_SCHEMA)
        self.assertEqual(question["kind"], "choice_change")
        self.assertEqual(question["recommended_candidate_ids"],
                         {"nominal": "a", "lower": "a", "upper": "b"})
        self.assertEqual(result["analysis"]["variables_checked"], 1)
        self.assertEqual(result["analysis"]["endpoint_rank_calls"], 2)
        self.assertIsNone(result["selected_candidate_id"])
        self.assertEqual(result["selection_status"], "not_selected")
        self.assertTrue(all(value is False for value in result["boundaries"].values()))

    def test_eligibility_change_without_choice_change_is_retained(self):
        request = _request()
        comparison = request["comparison_request"]
        comparison["actions"][1]["metrics"]["money"] = 0
        comparison["preferences"]["limits"] = {"money": 5}
        request["ranges"] = [_range("a", lower=1)]
        question = suggest_plan_measurements(request)["questions"][0]
        self.assertEqual(question["kind"], "eligibility_change")
        self.assertFalse(question["choice_changes"])
        self.assertEqual(question["eligibility_changes"], [
            {"candidate_id": "a", "nominal": "eligible", "lower": "eligible", "upper": "rejected"}])

    def test_required_unknown_without_range_is_not_imputed(self):
        request = _request()
        request["comparison_request"]["actions"][0]["metrics"]["money"] = None
        result = suggest_plan_measurements(request)
        self.assertEqual(result["questions"][0]["kind"], "required_unknown")
        self.assertIsNone(result["questions"][0]["nominal_value"])
        self.assertIsNone(result["questions"][0]["range"])
        self.assertEqual(result["analysis"]["endpoint_rank_calls"], 0)
        self.assertEqual(result["nominal_comparison"]["remaining_unknown_candidates"], ["a"])
        self.assertEqual(result["unresolved_required_unknowns"][0]["action_id"], "a")

    def test_irrelevant_metric_does_not_consume_probe_budget(self):
        request = _request()
        request["ranges"] = [_range("a", "energy_wh")]
        request["comparison_request"]["actions"][0]["metrics"]["tokens"] = None
        result = suggest_plan_measurements(request)
        self.assertEqual(result["questions"], [])
        self.assertEqual(result["analysis"]["variables_checked"], 0)
        self.assertEqual(result["unresolved_required_unknowns"], [])

    def test_unused_catalog_action_is_not_a_measurement_task(self):
        request = _request()
        request["comparison_request"]["actions"].append(_action("unused", money=None))
        request["ranges"] = [_range("unused")]
        result = suggest_plan_measurements(request)
        self.assertEqual(result["questions"], [])
        self.assertEqual(result["analysis"]["active_ranged_variables"], 0)

    def test_structurally_rejected_candidate_is_not_a_measurement_task(self):
        request = _request()
        request["comparison_request"]["actions"][0]["needs"] = ["missing"]
        request["ranges"] = [_range("a")]
        result = suggest_plan_measurements(request)
        self.assertEqual(result["questions"], [])
        self.assertEqual(result["analysis"]["variables_checked"], 0)

    def test_other_project_prefix_duration_feeds_project_deadline(self):
        request = _request()
        comparison = request["comparison_request"]
        comparison["projects"].append({"id": "q", "goals": ["done"]})
        comparison["actions"] = [_action("q-first", projects=("q",)), _action("p-last")]
        comparison["candidates"] = [{"id": "both", "steps": ["q-first", "p-last"],
                                     "goals": {"p": ["done"], "q": ["done"]}}]
        comparison["preferences"]["project_limits"] = {"p": {"elapsed_minutes": 3}}
        request["ranges"] = [_range("q-first", "elapsed_minutes", 0, 5)]
        result = suggest_plan_measurements(request)
        self.assertEqual(result["analysis"]["variables_checked"], 1)
        self.assertEqual(result["questions"][0]["action_id"], "q-first")
        self.assertIn({"project": "p", "metric": "elapsed_minutes"},
                      result["questions"][0]["required_for"])
        self.assertEqual(result["questions"][0]["eligibility_changes"][0]["upper"], "rejected")

    def test_nonbeneficiary_cost_and_duration_after_last_action_are_irrelevant(self):
        request = _request()
        comparison = request["comparison_request"]
        comparison["projects"].append({"id": "q", "goals": ["done"]})
        comparison["actions"] = [_action("p-first"), _action("q-last", projects=("q",))]
        comparison["candidates"] = [{"id": "both", "steps": ["p-first", "q-last"],
                                     "goals": {"p": ["done"], "q": ["done"]}}]
        comparison["preferences"] = {"priorities": [{"project": "p", "metric": "money"},
                                                     {"project": "p", "metric": "elapsed_minutes"}]}
        request["ranges"] = [_range("q-last"), _range("q-last", "elapsed_minutes", 0, 5)]
        self.assertEqual(suggest_plan_measurements(request)["analysis"]["variables_checked"], 0)

    def test_shared_unknown_has_one_question_for_all_beneficiaries(self):
        request = _request()
        comparison = request["comparison_request"]
        comparison["projects"].append({"id": "q", "goals": ["done"]})
        comparison["actions"] = [_action("shared", projects=("p", "q"), money=None)]
        comparison["candidates"] = [{"id": "both", "steps": ["shared"],
                                     "goals": {"p": ["done"], "q": ["done"]}}]
        comparison["candidates"].append({"id": "also", "steps": ["shared"],
                                         "goals": {"p": ["done"], "q": ["done"]}})
        comparison["preferences"] = {"priorities": [{"project": "p", "metric": "money"},
                                                     {"project": "q", "metric": "money"}]}
        questions = suggest_plan_measurements(request)["questions"]
        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0]["affected_candidate_ids"], ["also", "both"])
        self.assertEqual(questions[0]["required_for"],
                         [{"metric": "money", "project": "p"}, {"metric": "money", "project": "q"}])

    def test_unknown_ranged_cost_can_enable_comparison_without_nominal_winner(self):
        request = _request()
        comparison = request["comparison_request"]
        comparison["candidates"] = comparison["candidates"][:1]
        comparison["actions"][0]["metrics"]["money"] = None
        request["ranges"] = [_range("a")]
        result = suggest_plan_measurements(request)
        self.assertIsNone(result["nominal_recommended_candidate_id"])
        self.assertEqual(result["questions"][0]["recommended_candidate_ids"],
                         {"nominal": None, "lower": "a", "upper": "a"})

    def test_no_individual_flip_does_not_certify_interacting_uncertainties(self):
        request = _request()
        comparison = request["comparison_request"]
        comparison["actions"][0]["metrics"]["money"] = 2
        comparison["actions"].append(_action("a-extra", money=2))
        comparison["candidates"][0]["steps"].append("a-extra")
        request["ranges"] = [_range("a", lower=1, upper=3), _range("a-extra", lower=1, upper=3)]
        result = suggest_plan_measurements(request)
        self.assertEqual(result["questions"], [])
        self.assertEqual(result["status"], "no_one_factor_endpoint_change_detected")
        self.assertFalse(result["analysis"]["decision_stability_certified"])
        self.assertTrue(result["claim"]["joint_uncertainty_may_remain"])
        self.assertIsNone(result["claim"]["expected_value_of_information"])

    def test_check_budget_counts_variables_and_names_omissions(self):
        request = _request()
        request["ranges"] = [_range("b"), _range("a")]
        result = suggest_plan_measurements(request, max_checks=1)
        self.assertEqual(result["analysis"]["variables_checked"], 1)
        self.assertEqual(result["analysis"]["endpoint_rank_calls"], 2)
        self.assertEqual(result["analysis"]["variables_omitted"], 1)
        self.assertEqual(result["analysis"]["omitted_variables"], [{"action_id": "b", "metric": "money"}])
        self.assertFalse(result["analysis"]["complete"])
        self.assertTrue(result["analysis_incomplete"])

    def test_question_budget_retains_unknown_omissions_visibly(self):
        request = _request()
        comparison = request["comparison_request"]
        comparison["actions"][1]["metrics"]["money"] = None
        comparison["actions"].extend([_action("c", money=5), _action("d", money=4)])
        comparison["candidates"].extend([
            {"id": aid, "steps": [aid], "goals": {"p": ["done"]}} for aid in ("c", "d")])
        comparison["preferences"]["limits"] = {"money": 6}
        request["ranges"] = [_range("d", lower=3, upper=9), _range("a")]
        result = suggest_plan_measurements(request, max_questions=1)
        self.assertEqual(len(result["questions"]), 1)
        self.assertEqual(result["questions"][0]["action_id"], "a")
        self.assertEqual(result["questions"][0]["kind"], "choice_change")
        self.assertEqual(result["questions_omitted"], 2)
        self.assertTrue(result["questions_truncated"])
        self.assertEqual(len(result["unresolved_required_unknowns"]), 1)
        self.assertEqual(result["unresolved_required_unknowns"][0]["action_id"], "b")
        self.assertEqual([item["kind"] for item in suggest_plan_measurements(request)["questions"]],
                         ["choice_change", "eligibility_change", "required_unknown"])

    def test_budget_parameters_are_bounded_integers(self):
        for key, invalid in (("max_checks", [True, 0, 129, 1.0, "1"]),
                             ("max_questions", [True, 0, 17, 1.0, "1"])):
            for value in invalid:
                with self.subTest(parameter=key, value=value), self.assertRaises(ValueError):
                    suggest_plan_measurements(_request(), **{key: value})
        suggest_plan_measurements(_request(), max_checks=128, max_questions=16)

    def test_strict_envelope_validation_and_no_schema_budget_fields(self):
        for alter in (lambda item: item.update(max_checks=1),
                      lambda item: item.update(schema="wrong"),
                      lambda item: item.update(ranges=[_range("missing")]),
                      lambda item: item.update(ranges=[_range("a", upper=float("inf"))])):
            request = _request()
            alter(request)
            with self.assertRaises(ValueError):
                suggest_plan_measurements(request)

    def test_no_mutation_determinism_and_digest_binds_full_request(self):
        request = _request()
        request["ranges"] = [_range("a"), _range("b")]
        before = deepcopy(request)
        expected = suggest_plan_measurements(request)
        self.assertEqual(request, before)
        self.assertEqual(suggest_plan_measurements(request), expected)
        request["ranges"].reverse()
        request["comparison_request"]["actions"].reverse()
        request["comparison_request"]["candidates"].reverse()
        self.assertEqual(suggest_plan_measurements(request), expected)
        request["ranges"][0]["provenance"]["ref"] = "changed evidence"
        self.assertNotEqual(suggest_plan_measurements(request)["input_digest"], expected["input_digest"])

    def test_fixed_known_range_skips_probe_but_fixed_unknown_range_enables_it(self):
        request = _request()
        request["ranges"] = [_range("a", lower=1, upper=1)]
        self.assertEqual(suggest_plan_measurements(request)["analysis"]["variables_checked"], 0)
        request["comparison_request"]["actions"][0]["metrics"]["money"] = None
        result = suggest_plan_measurements(request)
        self.assertEqual(result["analysis"]["variables_checked"], 1)
        self.assertEqual(result["questions"][0]["kind"], "choice_change")

    def test_already_impossible_budget_candidate_does_not_request_measurement(self):
        request = _request()
        comparison = request["comparison_request"]
        comparison["actions"][0]["metrics"].update(money=None, energy_wh=10)
        comparison["preferences"]["limits"] = {"energy_wh": 5}
        result = suggest_plan_measurements(request)
        self.assertEqual(result["questions"], [])
        self.assertEqual(result["unresolved_required_unknowns"], [])

    def test_maximum_unknown_index_keeps_detailed_context_construction_bounded(self):
        request = _request()
        comparison = request["comparison_request"]
        project_ids = [f"p{index}" for index in range(32)]
        action_ids = [f"a{index}" for index in range(256)]
        comparison["projects"] = [{"id": pid, "goals": ["g"]} for pid in project_ids]
        comparison["actions"] = [
            {"id": aid, "needs": [], "projects": list(project_ids),
             "metrics": dict.fromkeys(METRICS),
             "provenance": {"kind": "estimate", "ref": "unknown fixture"}}
            for aid in action_ids]
        comparison["candidates"] = [
            {"id": f"c{index}", "steps": list(action_ids),
             "goals": {pid: ["g"] for pid in project_ids}}
            for index in range(64)]
        comparison["preferences"] = {
            "priorities": [{"metric": "money"}], "limits": dict.fromkeys(METRICS, 0),
            "project_limits": {pid: dict.fromkeys(METRICS, 0) for pid in project_ids}}
        self.assertLess(len(json.dumps(request).encode("utf-8")), MAX_INPUT_BYTES)
        with patch.object(measurement, "_context", wraps=measurement._context) as contexts:
            result = suggest_plan_measurements(request, max_questions=1)
        total = 256 * len(METRICS)
        self.assertEqual(contexts.call_count, MAX_UNKNOWN_CONTEXTS + 1)
        self.assertEqual(len(result["questions"]), 1)
        self.assertEqual(result["questions"][0]["kind"], "required_unknown")
        self.assertEqual(result["questions_omitted"], total - 1)
        self.assertEqual(result["unresolved_required_unknown_count"], total)
        index = result["unresolved_required_unknowns"]
        self.assertEqual(len(index), total)
        self.assertTrue(all(set(item) == {"action_id", "metric"} for item in index))
        self.assertEqual(len({(item["action_id"], item["metric"]) for item in index}), total)
        retained = result["unresolved_required_unknown_contexts"]
        self.assertEqual(len(retained), MAX_UNKNOWN_CONTEXTS)
        self.assertEqual(result["unresolved_required_unknown_contexts_omitted"], total - MAX_UNKNOWN_CONTEXTS)
        self.assertTrue(result["unresolved_required_unknown_contexts_truncated"])
        self.assertEqual(len(retained[0]["affected_candidate_ids"]), 64)
        self.assertEqual(len(retained[0]["required_for"]), 33)
        self.assertIsNone(result["questions"][0]["nominal_value"])
        self.assertEqual(len(result["nominal_comparison"]["remaining_unknown_candidates"]), 64)
        self.assertLess(len(json.dumps(result).encode("utf-8")), MAX_INPUT_BYTES)
        self.assertTrue(all(value is None for action in comparison["actions"]
                            for value in action["metrics"].values()))


if __name__ == "__main__":
    unittest.main()
