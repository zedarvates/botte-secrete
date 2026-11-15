"""Contracts for caller-supplied interval analysis, without sampling or I/O."""

from __future__ import annotations

import json
import unittest
from copy import deepcopy
from decimal import ROUND_UP, localcontext
from pathlib import Path

from skills.conductor.preferences import (
    MAX_INPUT_BYTES, METRICS, REQUEST_SCHEMA as COMPARISON_SCHEMA,
    parse_request_json, rank_plans,
)
from skills.conductor.uncertainty import (
    REQUEST_SCHEMA, RESULT_SCHEMA, analyse_plan_uncertainty, apply_range_values,
)


def _action(aid, *, money=1, elapsed=1, projects=("demo",), needs=()):
    return {"id": aid, "needs": list(needs), "projects": list(projects),
            "metrics": {metric: money if metric == "money" else elapsed if metric == "elapsed_minutes" else 1
                        for metric in METRICS},
            "provenance": {"kind": "estimate", "ref": "synthetic-fixture"}}


def _request():
    return {"schema": REQUEST_SCHEMA,
            "comparison_request": {
                "schema": COMPARISON_SCHEMA, "currency": "EUR",
                "projects": [{"id": "demo", "goals": ["done"]}],
                "actions": [_action("a", money=2), _action("b", money=7)],
                "candidates": [
                    {"id": "first", "steps": ["a"], "goals": {"demo": ["done"]}},
                    {"id": "second", "steps": ["b"], "goals": {"demo": ["done"]}}],
                "preferences": {"priorities": [{"metric": "money"}]}},
            "ranges": []}


def _range(aid, lower, upper, metric="money"):
    return {"action_id": aid, "metric": metric, "lower": lower, "upper": upper,
            "provenance": {"kind": "estimate", "ref": "synthetic-range"}}


def _candidate(report, cid="first"):
    return next(item for item in report["candidates"] if item["id"] == cid)


class PlanUncertaintyTests(unittest.TestCase):
    def test_exact_nominal_comparison_and_inputs_preserved(self):
        request = _request()
        original = deepcopy(request)
        report = analyse_plan_uncertainty(request)
        self.assertEqual(report["schema"], RESULT_SCHEMA)
        self.assertEqual(report["nominal_recommended_candidate_id"], "first")
        self.assertEqual(report["robust_recommended_candidate_id"], "first")
        self.assertEqual(_candidate(report)["lower_totals"], _candidate(report)["upper_totals"])
        self.assertEqual(request, original)
        self.assertIsNone(report["selected_candidate_id"])
        self.assertEqual(report["selection_status"], "not_selected")

    def test_separated_intervals_certify_recommendation(self):
        request = _request()
        request["ranges"] = [_range("a", 1, 3), _range("b", 6, 9)]
        report = analyse_plan_uncertainty(request)
        self.assertEqual(report["robust_recommended_candidate_id"], "first")
        self.assertTrue(_candidate(report)["robust_certificate"])
        self.assertFalse(_candidate(report, "second")["robust_certificate"])

    def test_overlapping_intervals_abstain(self):
        request = _request()
        request["ranges"] = [_range("a", 0, 8), _range("b", 3, 10)]
        report = analyse_plan_uncertainty(request)
        self.assertEqual(report["nominal_recommended_candidate_id"], "first")
        self.assertIsNone(report["robust_recommended_candidate_id"])

    def test_straddling_budget_is_uncertain(self):
        request = _request()
        request["comparison_request"]["preferences"]["limits"] = {"money": 3}
        request["ranges"] = [_range("a", 1, 4)]
        report = analyse_plan_uncertainty(request)
        self.assertEqual(_candidate(report)["budget_status"], "uncertain_limits")
        self.assertIsNone(report["robust_recommended_candidate_id"])

    def test_lower_budget_overrun_excludes_rival(self):
        request = _request()
        comparison = request["comparison_request"]
        comparison["preferences"]["limits"] = {"money": 3}
        comparison["actions"][1]["metrics"]["elapsed_minutes"] = None
        comparison["preferences"]["priorities"] = [{"metric": "elapsed_minutes"}]
        report = analyse_plan_uncertainty(request)
        self.assertEqual(_candidate(report, "second")["budget_status"], "exceeds_declared_limit")
        self.assertEqual(report["robust_recommended_candidate_id"], "first")

    def test_all_upper_global_and_project_limits_required(self):
        request = _request()
        request["ranges"] = [_range("a", 1, 3)]
        preferences = request["comparison_request"]["preferences"]
        preferences["limits"] = {"money": 3, "tokens": 1}
        preferences["project_limits"] = {"demo": {"money": 2}}
        self.assertEqual(_candidate(analyse_plan_uncertainty(request))["budget_status"], "uncertain_limits")
        preferences["project_limits"]["demo"]["money"] = 3
        self.assertEqual(_candidate(analyse_plan_uncertainty(request))["budget_status"], "within_declared_limits")

    def test_null_nominal_can_have_fully_declared_range(self):
        request = _request()
        request["comparison_request"]["actions"][0]["metrics"]["money"] = None
        request["ranges"] = [_range("a", 1, 3)]
        report = analyse_plan_uncertainty(request)
        self.assertEqual(report["nominal_recommended_candidate_id"], "second")
        self.assertEqual(_candidate(report)["nominal_status"], "undetermined")
        self.assertEqual(report["robust_recommended_candidate_id"], "first")
        self.assertEqual(report["fully_unknown_costs"], [])

    def test_fully_unknown_priority_rival_blocks_certificate(self):
        request = _request()
        request["comparison_request"]["actions"][1]["metrics"]["money"] = None
        report = analyse_plan_uncertainty(request)
        self.assertIsNone(report["robust_recommended_candidate_id"])
        rival = _candidate(report, "second")
        self.assertEqual(rival["lower_totals"]["money"], 0)
        self.assertIsNone(rival["upper_totals"]["money"])
        self.assertEqual(rival["unknown_priority_metrics"], [{"metric": "money"}])
        self.assertEqual(report["fully_unknown_costs"], [{"action_id": "b", "metric": "money"}])
        self.assertIn("never point estimates", report["bound_assumptions"][0])

    def test_unknown_irrelevant_metric_does_not_block_certificate(self):
        request = _request()
        request["comparison_request"]["actions"][0]["metrics"]["energy_wh"] = None
        report = analyse_plan_uncertainty(request)
        self.assertEqual(report["robust_recommended_candidate_id"], "first")
        self.assertEqual(_candidate(report)["unknown_priority_metrics"], [])

    def test_unknown_upper_budget_and_known_lower_contributions(self):
        request = _request()
        comparison = request["comparison_request"]
        comparison["actions"].append(_action("unknown", money=None))
        comparison["candidates"][0]["steps"].append("unknown")
        comparison["preferences"]["limits"] = {"money": 1}
        report = analyse_plan_uncertainty(request)
        first = _candidate(report)
        self.assertEqual(first["lower_totals"]["money"], 2)
        self.assertEqual(first["budget_status"], "exceeds_declared_limit")
        comparison["preferences"]["limits"]["money"] = 5
        self.assertEqual(_candidate(analyse_plan_uncertainty(request))["budget_status"], "uncertain_limits")

    def test_structural_dependency_rejection_survives_ranges(self):
        request = _request()
        request["comparison_request"]["actions"][0]["needs"] = ["absent"]
        request["ranges"] = [_range("a", 0, 2)]
        report = analyse_plan_uncertainty(request)
        self.assertEqual(_candidate(report)["structural_status"], "rejected")
        self.assertEqual(_candidate(report)["budget_status"], "exceeds_declared_limit")
        self.assertEqual(report["robust_recommended_candidate_id"], "second")
        self.assertEqual(_candidate(report)["structural_reasons"][0]["code"], "dependency_not_preceding")

    def test_goal_and_unknown_action_structural_rejections(self):
        for defect in ("goal", "action"):
            with self.subTest(defect=defect):
                request = _request()
                candidate = request["comparison_request"]["candidates"][0]
                if defect == "goal":
                    candidate["goals"] = {}
                else:
                    candidate["steps"].append("absent")
                report = analyse_plan_uncertainty(request)
                self.assertEqual(_candidate(report)["structural_status"], "rejected")
                self.assertEqual(report["robust_recommended_candidate_id"], "second")

    def test_correlated_shared_cost_keeps_box_certificate_conservative(self):
        request = _request()
        comparison = request["comparison_request"]
        comparison["actions"].append(_action("shared", money=50))
        for candidate in comparison["candidates"]:
            candidate["steps"].insert(0, "shared")
        request["ranges"] = [_range("shared", 0, 100)]
        report = analyse_plan_uncertainty(request)
        # A common additive cost cancels in an exact correlated comparison;
        # the intentionally conservative box comparison does not claim that.
        self.assertIsNone(report["robust_recommended_candidate_id"])
        self.assertEqual(report["nominal_recommended_candidate_id"], "first")
        self.assertIn("shared costs may be correlated", report["bound_assumptions"][2])

    def test_serial_ram_uses_maximum_of_endpoint_costs(self):
        request = _request()
        comparison = request["comparison_request"]
        comparison["actions"].append(_action("shared", money=0))
        comparison["candidates"][0]["steps"].append("shared")
        request["ranges"] = [_range("a", 1, 6, "peak_ram_gib"), _range("shared", 1, 4, "peak_ram_gib")]
        candidate = _candidate(analyse_plan_uncertainty(request))
        self.assertEqual(candidate["lower_totals"]["peak_ram_gib"], 1)
        self.assertEqual(candidate["upper_totals"]["peak_ram_gib"], 6)
        self.assertEqual(candidate["upper_totals"]["energy_wh"], 2)

    def test_full_beneficiary_cost_and_project_elapsed_prefix(self):
        request = _request()
        comparison = request["comparison_request"]
        comparison["projects"].append({"id": "plugin", "goals": ["done"]})
        comparison["actions"] = [
            _action("shared", money=2, elapsed=2, projects=("demo", "plugin")),
            _action("demo", money=3, elapsed=3),
            _action("plugin", money=4, elapsed=4, projects=("plugin",))]
        comparison["candidates"] = [{"id": "first", "steps": ["shared", "demo", "plugin"],
                                     "goals": {"demo": ["done"], "plugin": ["done"]}}]
        request["ranges"] = [_range("shared", 1, 3), _range("demo", 2, 8, "elapsed_minutes")]
        candidate = _candidate(analyse_plan_uncertainty(request))
        self.assertEqual(candidate["lower_totals"]["money"], 8)
        self.assertEqual(candidate["upper_project_totals"]["demo"]["money"], 6)
        self.assertEqual(candidate["upper_project_totals"]["plugin"]["money"], 7)
        self.assertEqual(candidate["lower_project_totals"]["plugin"]["elapsed_minutes"], 8)
        self.assertEqual(candidate["upper_project_totals"]["plugin"]["elapsed_minutes"], 14)
        self.assertEqual(candidate["upper_project_totals"]["demo"]["elapsed_minutes"], 10)

    def test_lexicographic_certificate_and_id_tiebreak(self):
        request = _request()
        comparison = request["comparison_request"]
        comparison["actions"][1]["metrics"]["money"] = 2
        comparison["preferences"]["priorities"].append({"metric": "elapsed_minutes"})
        request["ranges"] = [_range("a", 1, 2), _range("b", 2, 8)]
        self.assertEqual(analyse_plan_uncertainty(request)["robust_recommended_candidate_id"], "first")
        comparison["candidates"][0]["id"] = "z-first"
        self.assertIsNone(analyse_plan_uncertainty(request)["robust_recommended_candidate_id"])
        comparison["actions"][0]["metrics"]["elapsed_minutes"] = 0
        self.assertEqual(analyse_plan_uncertainty(request)["robust_recommended_candidate_id"], "z-first")

    def test_unknown_later_priority_blocks_even_strict_first_priority(self):
        request = _request()
        comparison = request["comparison_request"]
        comparison["preferences"]["priorities"].append({"metric": "tokens"})
        comparison["actions"][1]["metrics"]["tokens"] = None
        self.assertIsNone(analyse_plan_uncertainty(request)["robust_recommended_candidate_id"])

    def test_decimal_math_ignores_callers_context_and_float_addition(self):
        request = _request()
        comparison = request["comparison_request"]
        comparison["actions"][0]["metrics"]["money"] = 0.1
        comparison["actions"].append(_action("extra", money=0.2))
        comparison["candidates"][0]["steps"].append("extra")
        comparison["actions"][1]["metrics"]["money"] = 0.3
        comparison["preferences"]["limits"] = {"money": 0.3}
        with localcontext() as context:
            context.prec = 2
            context.rounding = ROUND_UP
            report = analyse_plan_uncertainty(request)
        self.assertEqual(_candidate(report)["budget_status"], "within_declared_limits")
        self.assertEqual(report["robust_recommended_candidate_id"], "first")
        # A tiny addend must remain visible to internal comparisons even when
        # the public float representation rounds the total back to 0.3.
        comparison["actions"].append(_action("tiny", money=5e-324))
        comparison["candidates"][0]["steps"].append("tiny")
        report = analyse_plan_uncertainty(request)
        self.assertEqual(_candidate(report)["budget_status"], "exceeds_declared_limit")
        self.assertEqual(report["robust_recommended_candidate_id"], "second")

    def test_catalogue_and_range_order_stability(self):
        request = _request()
        request["ranges"] = [_range("a", 1, 3), _range("b", 5, 9)]
        report = analyse_plan_uncertainty(request)
        reordered = deepcopy(request)
        reordered["comparison_request"]["actions"].reverse()
        reordered["comparison_request"]["candidates"].reverse()
        reordered["ranges"].reverse()
        self.assertEqual(analyse_plan_uncertainty(reordered), report)

    def test_full_envelope_digest_binds_ranges_and_provenance(self):
        request = _request()
        request["ranges"] = [_range("a", 1, 3)]
        first = analyse_plan_uncertainty(request)
        request["ranges"][0]["provenance"]["ref"] = "different-evidence"
        second = analyse_plan_uncertainty(request)
        self.assertNotEqual(first["input_digest"], second["input_digest"])
        self.assertEqual(first["comparison_input_digest"], second["comparison_input_digest"])
        self.assertEqual(second["ranges"], request["ranges"])

    def test_endpoint_helper_preserves_unbounded_nulls_and_input(self):
        request = _request()
        request["ranges"] = [_range("a", 1, 3)]
        request["comparison_request"]["actions"][1]["metrics"]["money"] = None
        request["comparison_request"]["actions"][0]["provenance"] = {
            "kind": "measurement", "ref": "observed-run-123"}
        original = deepcopy(request)
        lower = apply_range_values(request, "lower")
        upper = apply_range_values(request, "upper")
        self.assertEqual(lower["actions"][0]["metrics"]["money"], 1)
        self.assertEqual(upper["actions"][0]["metrics"]["money"], 3)
        self.assertIsNone(lower["actions"][1]["metrics"]["money"])
        digest = analyse_plan_uncertainty(request)["input_digest"]
        self.assertEqual(upper["actions"][0]["provenance"], {
            "kind": "estimate", "ref": f"uncertainty-upper:{digest}"})
        self.assertEqual(lower["actions"][0]["provenance"]["ref"], f"uncertainty-lower:{digest}")
        self.assertNotEqual(upper["actions"][0]["provenance"], original["comparison_request"]["actions"][0]["provenance"])
        self.assertEqual(upper, apply_range_values(request, "upper"))
        self.assertLessEqual(len(upper["actions"][0]["provenance"]["ref"]), 512)
        self.assertEqual(upper["actions"][1]["provenance"], original["comparison_request"]["actions"][1]["provenance"])
        lower["actions"][0]["provenance"]["ref"] = "changed-copy"
        self.assertEqual(request, original)
        request["ranges"][0]["lower"] = request["ranges"][0]["upper"] = 2
        projected = apply_range_values(request, "upper")
        self.assertEqual(projected["actions"][0]["provenance"]["kind"], "estimate")
        self.assertTrue(projected["actions"][0]["provenance"]["ref"].startswith("uncertainty-upper:"))
        self.assertEqual(analyse_plan_uncertainty(request)["ranges"], request["ranges"])
        with self.assertRaises(ValueError):
            apply_range_values(request, "midpoint")

    def test_malformed_ranges_raise_value_error(self):
        changes = [
            {"lower": -1}, {"upper": 10 ** 15 + 1}, {"lower": 3, "upper": 2},
            {"lower": 3, "upper": 4}, {"lower": True}, {"upper": None},
            {"upper": float("nan")}, {"lower": float("inf")},
            {"action_id": "absent"}, {"metric": "duration"}, {"unexpected": 1},
            {"provenance": {"kind": "prediction", "ref": "x"}},
            {"provenance": {"kind": "estimate", "ref": ""}},
            {"provenance": {"kind": "estimate", "ref": "x", "unknown": 1}},
        ]
        for change in changes:
            with self.subTest(change=change):
                request = _request()
                item = _range("a", 1, 3)
                item.update(change)
                request["ranges"] = [item]
                with self.assertRaises(ValueError):
                    analyse_plan_uncertainty(request)
        request = _request()
        request["ranges"] = [_range("a", 1, 3)] * 2
        with self.assertRaises(ValueError):
            analyse_plan_uncertainty(request)

    def test_bounded_strict_envelope_and_json_parsing(self):
        for key, value in (("extra", 1), ("schema", COMPARISON_SCHEMA), ("ranges", {})):
            with self.subTest(key=key):
                request = _request()
                request[key] = value
                with self.assertRaises(ValueError):
                    analyse_plan_uncertainty(request)
        nested = []
        for _ in range(65):
            nested = [nested]
        request = _request()
        request["extra"] = nested
        with self.assertRaisesRegex(ValueError, "64 nesting"):
            analyse_plan_uncertainty(request)
        request = _request()
        request["extra"] = "x" * MAX_INPUT_BYTES
        with self.assertRaisesRegex(ValueError, "1 MiB"):
            analyse_plan_uncertainty(request)
        for raw in ('{"schema":1,"schema":2}', '{"value":NaN}', '{"value":1e999}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_request_json(raw)

    def test_existing_rank_contract_unchanged_and_strict(self):
        request = _request()
        comparison = request["comparison_request"]
        before = rank_plans(comparison)
        analyse_plan_uncertainty(request)
        self.assertEqual(rank_plans(comparison), before)
        comparison["ranges"] = []
        with self.assertRaises(ValueError):
            rank_plans(comparison)
        with self.assertRaises(ValueError):
            analyse_plan_uncertainty(request)

    def test_example_is_an_explicit_unverified_advisory(self):
        path = Path(__file__).resolve().parents[2] / "examples" / "parcimonia_plan_uncertainty.json"
        report = analyse_plan_uncertainty(parse_request_json(path.read_text(encoding="utf-8")))
        self.assertFalse(report["claim"]["ranges_verified"])
        self.assertFalse(report["claim"]["universal_optimality"])
        self.assertFalse(any(report["boundaries"].values()))
        self.assertIsNone(report["selected_candidate_id"])
        self.assertEqual(report["selection_status"], "not_selected")


if __name__ == "__main__":
    unittest.main()
