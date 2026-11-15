"""Contract checks for the isolated, same-objective validation pilot."""

from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from scripts import plan_validation_pilot as pilot
from skills.conductor.verified import execute_verified


class PlanValidationPilotTests(unittest.TestCase):
    def test_strategies_cover_the_identical_twelve_test_ids_once(self):
        self.assertEqual(len(pilot.TEST_IDS), 12)
        self.assertEqual(len(set(pilot.TEST_IDS)), 12)
        for groups in pilot.strategies().values():
            self.assertEqual(tuple(test for group in groups for test in group), pilot.TEST_IDS)

    def test_missing_method_loader_error_is_retained_and_never_accepted(self):
        missing = "skills.conductor.test_preferences.PlanPreferencesTests.test_missing_pilot_contract"
        result = pilot.run_test_ids([missing])
        self.assertFalse(pilot.accepted_result(result, [missing]))
        self.assertFalse(result["all_passed"])
        self.assertEqual(len(result["errors"]), 1)
        self.assertIn("test_missing_pilot_contract", result["errors"][0]["detail"])

    def test_verifier_rejects_missing_duplicate_skipped_and_false_success_evidence(self):
        ids = pilot.TEST_IDS[:1]
        result = pilot.run_test_ids(ids)
        self.assertTrue(pilot.accepted_result(result, ids))
        for mutation in (
            lambda item: item.update(executed_test_ids=[]),
            lambda item: item.update(executed_test_ids=list(ids) * 2),
            lambda item: item.update(tests_run=True),
            lambda item: item.update(skipped=[{"test_id": ids[0], "reason": "unavailable"}]),
            lambda item: item.update(errors=[{"test_id": ids[0], "detail": "failed"}]),
        ):
            altered = deepcopy(result)
            mutation(altered)
            self.assertFalse(pilot.accepted_result(altered, ids))

    def test_source_drift_blocks_real_dispatch_before_any_result_is_written(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            hashes = pilot.snapshot_sources(Path(__file__).resolve().parents[1], root)
            plan = pilot.build_plan(root, "batched", 1, hashes)
            (root / "skills/conductor/preferences.py").write_text("changed\n", encoding="utf-8")
            report = execute_verified(plan, cwd=str(root), confirm=True, timeout=5)
            self.assertFalse(report["complete"])
            self.assertEqual(report["results"][0]["status"], "blocked")
            self.assertFalse(report["results"][0]["started"])
            self.assertFalse((root / plan["steps"][0]["observes"][0]).exists())

    def test_preview_writes_only_explicit_report_and_dispatches_nothing(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "preview.json"
            with patch("subprocess.run", side_effect=AssertionError("preview dispatched")):
                self.assertEqual(pilot.main(["--output", str(output)]), 0)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["runs"], [])
            self.assertFalse(report["complete"])
            self.assertEqual(list(Path(temporary).iterdir()), [output])

    def test_real_paired_run_is_complete_with_same_accepted_objective(self):
        report = pilot.run_pilot(Path(__file__).resolve().parents[1], repetitions=1,
                                 timeout=10, run=True)
        self.assertTrue(report["complete"], report["failures"])
        self.assertEqual([row["processes_started"] for row in report["runs"]], [1, 4])
        self.assertTrue(report["snapshot_sources_unchanged"])
        self.assertTrue(report["source_tree_files_unchanged"])
        self.assertIsNone(report["usage"]["energy_wh"])
        for row in report["runs"]:
            self.assertTrue(row["execution"]["complete"])
            self.assertEqual([name for result in row["test_outputs"]
                              for name in result["executed_test_ids"]], list(pilot.TEST_IDS))
            self.assertTrue(all(result["source_checks"]
                                for result in row["execution"]["results"]))
        comparison = report["retrospective_comparison"]
        self.assertIsNone(comparison["proposals"]["selected_candidate_id"])
        for action in comparison["request"]["actions"]:
            self.assertGreater(action["metrics"]["elapsed_minutes"], 0)
            self.assertTrue(all(value is None for key, value in action["metrics"].items()
                                if key != "elapsed_minutes"))
        failed = deepcopy(report["runs"])
        failed[0]["accepted"] = False
        comparison = pilot.retrospective_comparison(failed)
        self.assertNotEqual(comparison["proposals"]["recommended_candidate_id"], "batched")
        self.assertIsNone(comparison["request"]["actions"][0]["metrics"]["elapsed_minutes"])
        failed[1]["accepted"] = False
        self.assertIsNone(pilot.retrospective_comparison(failed)["proposals"]["recommended_candidate_id"])
        comparison = pilot.retrospective_comparison(report["runs"], repetitions=2)
        self.assertIsNone(comparison["proposals"]["recommended_candidate_id"])


if __name__ == "__main__":
    unittest.main()
