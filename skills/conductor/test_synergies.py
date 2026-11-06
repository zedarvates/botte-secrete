"""Whole-candidate sharing comparisons without inference or execution."""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, ROUND_UP, localcontext
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from skills.conductor.preferences import METRICS, parse_request_json, rank_plans
from skills.conductor.synergies import (
    MAX_CHANGED_ACTIONS, MAX_INPUT_BYTES, MAX_OPPORTUNITIES, MAX_REPORT_BYTES,
    REQUEST_SCHEMA, RESULT_SCHEMA, analyse_plan_synergies,
)


def _action(aid, projects, *, needs=(), elapsed=1, money=1, ram=1):
    return {"id": aid, "needs": list(needs), "projects": list(projects),
            "metrics": {metric: elapsed if metric == "elapsed_minutes" else
                        money if metric == "money" else ram if metric == "peak_ram_gib" else 1
                        for metric in METRICS},
            "provenance": {"kind": "estimate", "ref": "synthetic-sharing-case-not-a-benchmark"}}


def _request():
    return {
        "schema": REQUEST_SCHEMA,
        "comparison_request": {
            "schema": "parcimonia.plan-preferences/v1", "currency": "EUR",
            "projects": [{"id": "p", "goals": ["done"]}, {"id": "q", "goals": ["done"]}],
            "actions": [
                _action("prepare-p", ["p"], elapsed=2, money=4, ram=2),
                _action("prepare-q", ["q"], elapsed=2, money=4, ram=3),
                _action("prepare-shared", ["p", "q"], elapsed=3, money=6, ram=4),
                _action("finish-p", ["p"], needs=["prepare-p"]),
                _action("finish-q", ["q"], needs=["prepare-q"]),
                _action("finish-p-shared", ["p"], needs=["prepare-shared"]),
                _action("finish-q-shared", ["q"], needs=["prepare-shared"]),
            ],
            "candidates": [
                {"id": "separate", "steps": ["prepare-p", "finish-p", "prepare-q", "finish-q"],
                 "goals": {"p": ["done"], "q": ["done"]}},
                {"id": "combined", "steps": ["prepare-shared", "finish-q-shared", "finish-p-shared"],
                 "goals": {"p": ["done"], "q": ["done"]}},
            ],
            "preferences": {"priorities": [{"metric": "elapsed_minutes"}]},
        },
        "opportunities": [{"id": "shared-preparation", "baseline_candidate_id": "separate",
                           "shared_candidate_id": "combined", "separate_action_ids": ["prepare-p", "prepare-q"],
                           "shared_action_id": "prepare-shared", "assumption_ref": "caller-declared-equivalence"}],
    }


def _candidate(report, cid):
    return next(item for item in report["candidates"] if item["id"] == cid)


class PlanSynergiesTests(unittest.TestCase):
    def test_whole_candidate_totals_reuse_comparator_and_leave_input_unchanged(self):
        request = _request()
        original = deepcopy(request)
        expected = rank_plans(request["comparison_request"])
        report = analyse_plan_synergies(request)
        self.assertEqual(report["schema"], RESULT_SCHEMA)
        self.assertEqual(report["comparison_input_digest"], expected["input_digest"])
        self.assertEqual(report["ranking"], expected["ranking"])
        self.assertEqual(report["recommended_candidate_id"], "combined")
        for candidate in expected["candidates"]:
            actual = _candidate(report, candidate["id"])
            self.assertEqual(actual["totals"], candidate["totals"])
            self.assertEqual(actual["project_totals"], candidate["project_totals"])
        self.assertEqual(request, original)
        self.assertIsNone(report["selected_candidate_id"])
        self.assertEqual(report["selection_status"], "not_selected")
        self.assertFalse(report["execution_authorized"])
        self.assertIsNone(report["claims"]["measured_gain"])

    def test_whole_and_group_deltas_include_project_prefix_and_ram_max(self):
        report = analyse_plan_synergies(_request())
        opportunity = report["opportunities"][0]
        self.assertEqual(opportunity["status"], "compared")
        self.assertEqual(opportunity["global_delta"]["elapsed_minutes"], -1)
        self.assertEqual(opportunity["global_delta"]["money"], -2)
        self.assertEqual(opportunity["project_deltas"]["p"]["elapsed_minutes"], 2)
        self.assertEqual(opportunity["project_deltas"]["q"]["elapsed_minutes"], -2)
        self.assertEqual(opportunity["group_metrics"]["separate_totals"]["peak_ram_gib"], 3)
        self.assertEqual(opportunity["group_metrics"]["shared_totals"]["peak_ram_gib"], 4)
        self.assertEqual(opportunity["group_metrics"]["delta"]["peak_ram_gib"], 1)
        self.assertEqual(opportunity["global_delta"]["peak_ram_gib"], 1)
        self.assertFalse(opportunity["attribution_to_sharing_verified"])

    def test_urgent_project_priority_changes_the_preferred_path(self):
        request = _request()
        fast = analyse_plan_synergies(request)
        self.assertEqual(fast["opportunities"][0]["preferred_eligible_candidate_id"], "combined")
        request["comparison_request"]["preferences"]["priorities"] = [
            {"metric": "elapsed_minutes", "project": "p"}, {"metric": "elapsed_minutes"}]
        urgent = analyse_plan_synergies(request)
        self.assertEqual(urgent["recommended_candidate_id"], "separate")
        self.assertEqual(urgent["opportunities"][0]["preferred_eligible_candidate_id"], "separate")
        self.assertNotEqual(fast["input_digest"], urgent["input_digest"])

    def test_full_beneficiary_budget_can_reject_globally_cheaper_shared_plan(self):
        request = _request()
        request["comparison_request"]["preferences"]["project_limits"] = {"p": {"money": 6}}
        report = analyse_plan_synergies(request)
        opportunity = report["opportunities"][0]
        self.assertEqual(_candidate(report, "combined")["status"], "rejected")
        self.assertEqual(opportunity["status"], "compared")
        self.assertEqual(opportunity["global_delta"]["money"], -2)
        self.assertEqual(opportunity["project_deltas"]["p"]["money"], 2)
        self.assertEqual(opportunity["preferred_eligible_candidate_id"], "separate")

    def test_unknown_metrics_stay_null_without_blocking_other_differences(self):
        request = _request()
        request["comparison_request"]["actions"][0]["metrics"]["money"] = None
        report = analyse_plan_synergies(request)
        opportunity = report["opportunities"][0]
        self.assertIsNone(opportunity["global_delta"]["money"])
        self.assertIsNone(opportunity["project_deltas"]["p"]["money"])
        self.assertIsNone(opportunity["group_metrics"]["delta"]["money"])
        self.assertEqual(opportunity["global_delta"]["elapsed_minutes"], -1)
        request["comparison_request"]["preferences"]["priorities"] = [{"metric": "money"}]
        report = analyse_plan_synergies(request)
        self.assertEqual(_candidate(report, "separate")["status"], "undetermined")
        self.assertEqual(report["opportunities"][0]["status"], "compared")

    def test_no_eligible_pair_plan_remains_unselected_and_unpreferred(self):
        request = _request()
        request["comparison_request"]["preferences"]["limits"] = {"money": 0}
        report = analyse_plan_synergies(request)
        self.assertEqual(report["ranking"], [])
        self.assertIsNone(report["recommended_candidate_id"])
        self.assertIsNone(report["opportunities"][0]["preferred_eligible_candidate_id"])
        self.assertEqual(report["opportunities"][0]["status"], "compared")

    def test_changed_consumers_are_visible_and_not_attributed_to_sharing(self):
        request = _request()
        request["comparison_request"]["actions"][5]["metrics"]["money"] = 50
        report = analyse_plan_synergies(request)
        opportunity = report["opportunities"][0]
        self.assertEqual(opportunity["group_metrics"]["delta"]["money"], -2)
        self.assertEqual(opportunity["global_delta"]["money"], 47)
        self.assertEqual(opportunity["action_changes"]["added"]["ids"],
                         ["finish-p-shared", "finish-q-shared", "prepare-shared"])
        self.assertEqual(opportunity["action_changes"]["removed"]["count"], 4)
        self.assertFalse(opportunity["attribution_to_sharing_verified"])
        self.assertEqual(report["recommended_candidate_id"], "combined")
        request["comparison_request"]["preferences"]["priorities"] = [{"metric": "money"}]
        self.assertEqual(analyse_plan_synergies(request)["recommended_candidate_id"], "separate")

    def test_invalid_dependency_order_unqualifies_pair_and_nulls_all_deltas(self):
        request = _request()
        request["comparison_request"]["candidates"][1]["steps"] = [
            "finish-q-shared", "prepare-shared", "finish-p-shared"]
        report = analyse_plan_synergies(request)
        opportunity = report["opportunities"][0]
        self.assertEqual(opportunity["status"], "unqualified")
        self.assertTrue(all(value is None for value in opportunity["global_delta"].values()))
        self.assertTrue(all(value is None for value in opportunity["group_metrics"]["delta"].values()))
        self.assertTrue(all(value is None for metrics in opportunity["project_deltas"].values()
                            for value in metrics.values()))
        self.assertIsNone(opportunity["preferred_eligible_candidate_id"])
        self.assertEqual(_candidate(report, "combined")["reason_counts"]["dependency_not_preceding"], 1)

    def test_missing_action_or_goal_is_structurally_unqualified(self):
        for mutation in ("missing_action", "missing_goal"):
            request = _request()
            if mutation == "missing_action":
                request["comparison_request"]["candidates"][0]["steps"].append("not-in-catalogue")
            else:
                for candidate in request["comparison_request"]["candidates"]:
                    candidate["goals"].pop("q")
            with self.subTest(mutation=mutation):
                self.assertEqual(analyse_plan_synergies(request)["opportunities"][0]["status"], "unqualified")

    def test_decimal_subtraction_happens_before_public_rounding(self):
        request = _request()
        for action in request["comparison_request"]["actions"]:
            action["metrics"]["money"] = 0
        request["comparison_request"]["actions"][0]["metrics"]["money"] = 10 ** 15
        request["comparison_request"]["actions"][1]["metrics"]["money"] = 0.01
        request["comparison_request"]["actions"][2]["metrics"]["money"] = 10 ** 15
        report = analyse_plan_synergies(request)
        self.assertEqual(_candidate(report, "combined")["totals"]["money"],
                         _candidate(report, "separate")["totals"]["money"])
        self.assertEqual(report["opportunities"][0]["global_delta"]["money"], -0.01)
        self.assertEqual(report["opportunities"][0]["group_metrics"]["delta"]["money"], -0.01)

    def test_decimal_context_of_caller_does_not_change_result(self):
        request = _request()
        expected = analyse_plan_synergies(request)
        with localcontext() as context:
            context.prec = 2
            context.rounding = ROUND_UP
            self.assertEqual(analyse_plan_synergies(request), expected)

    def test_underflowed_nonzero_delta_keeps_its_exact_value_and_direction(self):
        request = _request()
        for action in request["comparison_request"]["actions"]:
            action["metrics"]["money"] = 0
        request["comparison_request"]["actions"][0]["metrics"]["money"] = 4e-323
        request["comparison_request"]["actions"][1]["metrics"]["money"] = 5e-324
        request["comparison_request"]["actions"][2]["metrics"]["money"] = 4.4e-323
        request["comparison_request"]["preferences"]["priorities"] = [{"metric": "money"}]
        report = analyse_plan_synergies(request)
        opportunity = report["opportunities"][0]
        self.assertEqual(opportunity["global_delta"]["money"], 0)
        exact = report["exact_delta_values"]
        self.assertEqual(exact[opportunity["delta_rounding"]["global"]["money"]], "-1E-324")
        self.assertEqual(exact[opportunity["delta_rounding"]["group"]["money"]], "-1E-324")
        self.assertEqual(report["recommended_candidate_id"], "combined")
        self.assertEqual(report["preferences"], request["comparison_request"]["preferences"])
        self.assertEqual(report["remaining_unknown_candidates"], [])
        self.assertEqual(report["optimality_scope"], "known_eligible_candidates_only")

    def test_exact_numeric_deltas_need_no_rounding_companions(self):
        report = analyse_plan_synergies(_request())
        opportunity = report["opportunities"][0]
        self.assertEqual(opportunity["delta_rounding"], {"global": {}, "projects": {}, "group": {}})
        self.assertEqual(report["exact_delta_values"], [])

    def test_repeated_long_exact_deltas_are_interned_within_report_budget(self):
        request = _request()
        comparison = request["comparison_request"]
        projects = [f"p{i:02d}" for i in range(32)]
        comparison["projects"] = [{"id": pid, "goals": ["done"]} for pid in projects]
        large = _action("large", projects)
        tiny = _action("tiny", projects)
        shared = _action("shared", projects)
        for metric in METRICS:
            large["metrics"][metric] = 10 ** 15
            tiny["metrics"][metric] = 5e-324
            shared["metrics"][metric] = 0
        tags = [_action(f"tag-{i:02d}", projects) for i in range(32)]
        for tag in tags:
            tag["metrics"] = {metric: 0 for metric in METRICS}
        comparison["actions"] = [large, tiny, shared, *tags]
        goals = {pid: ["done"] for pid in projects}
        comparison["candidates"] = [
            {"id": "separate", "steps": ["large", "tiny", *[tag["id"] for tag in tags]], "goals": goals},
            {"id": "combined", "steps": ["shared"], "goals": deepcopy(goals)},
        ]
        request["opportunities"] = [
            {"id": f"sharing-{i:02d}", "baseline_candidate_id": "separate", "shared_candidate_id": "combined",
             "separate_action_ids": ["large", "tiny", tag["id"]], "shared_action_id": "shared",
             "assumption_ref": "synthetic-dense-rounding-case"} for i, tag in enumerate(tags)]
        report = analyse_plan_synergies(request)
        self.assertLess(len(json.dumps(report, separators=(",", ":")).encode("utf-8")), MAX_REPORT_BYTES)
        self.assertEqual(len(report["exact_delta_values"]), 1)
        for opportunity in report["opportunities"]:
            index = opportunity["delta_rounding"]["global"]["money"]
            with localcontext() as context:
                context.prec = 350
                expected = -(Decimal(10 ** 15) + Decimal("5e-324"))
                self.assertEqual(Decimal(report["exact_delta_values"][index]), expected)
            self.assertEqual(opportunity["delta_rounding"]["projects"][projects[0]]["money"], index)
            self.assertEqual(opportunity["delta_rounding"]["group"]["money"], index)

    def test_set_like_order_is_canonical_but_step_order_changes_digest(self):
        request = _request()
        original = analyse_plan_synergies(request)
        request["comparison_request"]["actions"].reverse()
        request["comparison_request"]["projects"].reverse()
        request["comparison_request"]["candidates"].reverse()
        request["opportunities"][0]["separate_action_ids"].reverse()
        self.assertEqual(analyse_plan_synergies(request), original)
        request["comparison_request"]["candidates"][0]["steps"] = [
            "prepare-shared", "finish-p-shared", "finish-q-shared"]
        changed = analyse_plan_synergies(request)
        self.assertNotEqual(changed["input_digest"], original["input_digest"])

    def test_costs_and_assumption_changes_bind_the_report_digest(self):
        original = _request()
        before = analyse_plan_synergies(original)
        for change in ("cost", "assumption", "opportunity_id"):
            request = deepcopy(original)
            if change == "cost":
                request["comparison_request"]["actions"][0]["metrics"]["money"] += 1
            elif change == "assumption":
                request["opportunities"][0]["assumption_ref"] = "another-equivalence-assumption"
            else:
                request["opportunities"][0]["id"] = "renamed"
            with self.subTest(change=change):
                self.assertNotEqual(analyse_plan_synergies(request)["input_digest"], before["input_digest"])

    def test_empty_opportunity_list_is_valid_analysis_without_inference(self):
        request = _request()
        request["opportunities"] = []
        report = analyse_plan_synergies(request)
        self.assertEqual(report["opportunities"], [])
        self.assertEqual(report["recommended_candidate_id"], "combined")

    def test_contradictory_candidate_and_action_bindings_are_rejected(self):
        mutations = [
            ("baseline_candidate_id", "unknown"), ("shared_candidate_id", "separate"),
            ("separate_action_ids", ["prepare-p"]),
            ("separate_action_ids", ["prepare-p", "prepare-p"]),
            ("separate_action_ids", ["prepare-p", "unknown"]),
            ("separate_action_ids", ["prepare-p", "finish-p-shared"]),
            ("shared_action_id", "prepare-p"), ("shared_action_id", "unknown"),
        ]
        for field, value in mutations:
            request = _request()
            request["opportunities"][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                analyse_plan_synergies(request)

    def test_candidates_with_different_goal_sets_are_not_comparable(self):
        request = _request()
        request["comparison_request"]["candidates"][0]["goals"].pop("p")
        with self.assertRaisesRegex(ValueError, "same goals"):
            analyse_plan_synergies(request)

    def test_beneficiary_union_is_exact_and_cross_project(self):
        request = _request()
        request["comparison_request"]["actions"][2]["projects"] = ["p"]
        with self.assertRaisesRegex(ValueError, "member union"):
            analyse_plan_synergies(request)
        request = _request()
        request["comparison_request"]["actions"][1]["projects"] = ["p"]
        request["comparison_request"]["actions"][2]["projects"] = ["p"]
        with self.assertRaisesRegex(ValueError, "member union"):
            analyse_plan_synergies(request)

    def test_duplicate_ids_and_duplicate_bindings_even_with_new_ref_are_rejected(self):
        request = _request()
        item = deepcopy(request["opportunities"][0])
        request["opportunities"].append(item)
        with self.assertRaisesRegex(ValueError, "duplicate opportunity id"):
            analyse_plan_synergies(request)
        item["id"] = "another"
        item["assumption_ref"] = "another-reference"
        item["separate_action_ids"].reverse()
        with self.assertRaisesRegex(ValueError, "duplicate opportunity binding"):
            analyse_plan_synergies(request)

    def test_closed_fields_schema_reference_types_and_opportunity_limit(self):
        cases = [("schema", "wrong"), ("extra", True), ("opportunities", {}),
                 ("opportunities", [deepcopy(_request()["opportunities"][0])] * (MAX_OPPORTUNITIES + 1))]
        for field, value in cases:
            request = _request()
            request[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                analyse_plan_synergies(request)
        for value in ("", "x" * 513, None, True):
            request = _request()
            request["opportunities"][0]["assumption_ref"] = value
            with self.subTest(reference=value), self.assertRaises(ValueError):
                analyse_plan_synergies(request)
        request = _request()
        request["opportunities"][0]["execute"] = True
        with self.assertRaises(ValueError):
            analyse_plan_synergies(request)

    def test_duplicate_json_nonfinite_depth_types_and_size_are_rejected(self):
        for raw in ('{"schema":"a","schema":"b"}', '{"value":NaN}', '{"value":1e999}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                analyse_plan_synergies(parse_request_json(raw))
        for value in (float("nan"), float("inf"), object(), {1: "non-json-key"}):
            request = _request()
            request["extra"] = value
            with self.subTest(value=str(value)), self.assertRaises(ValueError):
                analyse_plan_synergies(request)
        deep = []
        for _ in range(70):
            deep = [deep]
        request = _request()
        request["extra"] = deep
        with self.assertRaises(ValueError):
            analyse_plan_synergies(request)
        request["extra"] = "x" * (MAX_INPUT_BYTES + 1)
        with self.assertRaises(ValueError):
            analyse_plan_synergies(request)

    def test_compact_reason_samples_keep_full_counts_and_goal_omissions(self):
        request = _request()
        comparison = request["comparison_request"]
        for i in range(12):
            pid = f"missing-{i}"
            comparison["projects"].append({"id": pid, "goals": [f"goal-{j}" for j in range(16)]})
        report = analyse_plan_synergies(request)
        summary = _candidate(report, "separate")
        self.assertEqual(len(summary["reasons"]), 8)
        self.assertEqual(sum(summary["reason_counts"].values()), 24)
        self.assertEqual(summary["reasons_omitted"], 16)
        reason = next(item for item in summary["reasons"] if item["code"] == "goals_not_declared")
        self.assertEqual(len(reason["goals"]), 4)
        self.assertEqual(reason["goal_count"], 16)
        self.assertEqual(reason["goals_omitted"], 12)
        self.assertEqual(report["opportunities"][0]["status"], "unqualified")

    def test_changed_action_samples_keep_exact_counts(self):
        request = _request()
        comparison = request["comparison_request"]
        for i in range(40):
            aid = f"extra-{i:02d}"
            comparison["actions"].append(_action(aid, ["p"]))
            comparison["candidates"][1]["steps"].append(aid)
        report = analyse_plan_synergies(request)
        added = report["opportunities"][0]["action_changes"]["added"]
        self.assertEqual(added["count"], 43)
        self.assertEqual(len(added["ids"]), MAX_CHANGED_ACTIONS)
        self.assertEqual(added["omitted"], 43 - MAX_CHANGED_ACTIONS)

    def test_structural_rejection_beyond_displayed_reasons_stays_unqualified(self):
        request = _request()
        comparison = request["comparison_request"]
        for i in range(12):
            aid = f"unknown-{i}"
            comparison["candidates"][1]["steps"].insert(0, aid)
        report = analyse_plan_synergies(request)
        summary = _candidate(report, "combined")
        self.assertEqual(summary["reason_counts"]["unknown_action"], 12)
        self.assertEqual(summary["structural_status"], "rejected")
        self.assertEqual(len(summary["reasons"]), 8)
        self.assertEqual(summary["reasons_omitted"], 5)
        self.assertEqual(report["opportunities"][0]["status"], "unqualified")

    def test_report_limit_is_enforced_without_returning_a_partial_document(self):
        with patch("skills.conductor.synergies.MAX_REPORT_BYTES", 200), self.assertRaisesRegex(ValueError, "report"):
            analyse_plan_synergies(_request())
        self.assertLess(len(json.dumps(analyse_plan_synergies(_request())).encode("utf-8")), MAX_REPORT_BYTES)

    def test_no_model_network_execution_storage_or_telemetry_calls(self):
        with patch("subprocess.Popen", side_effect=AssertionError("execution")), \
                patch("socket.socket", side_effect=AssertionError("network")), \
                patch("pathlib.Path.open", side_effect=AssertionError("storage")), \
                patch("skills.events.log_event", side_effect=AssertionError("telemetry")):
            report = analyse_plan_synergies(_request())
        self.assertTrue(all(value is False for value in report["boundaries"].values()))

    def test_example_is_valid_and_preserves_explicit_choices(self):
        root = Path(__file__).resolve().parents[2]
        request = parse_request_json((root / "examples/parcimonia_plan_synergies.json").read_text(encoding="utf-8"))
        report = analyse_plan_synergies(request)
        self.assertEqual(len(report["opportunities"]), 1)
        self.assertEqual(report["opportunities"][0]["status"], "compared")
        self.assertIsNone(report["selected_candidate_id"])


if __name__ == "__main__":
    unittest.main()
