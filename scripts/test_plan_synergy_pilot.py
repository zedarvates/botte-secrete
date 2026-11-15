"""Fixed-pilot scope, real output oracles, explicit choice and sharing counts."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import plan_synergy_pilot as pilot
from skills.conductor.verified import execute_verified


class PlanSynergyPilotTests(unittest.TestCase):
    def test_default_preview_only_saves_requested_report_without_dispatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "preview.json"
            with patch("subprocess.run", side_effect=AssertionError("preview dispatched")), \
                    patch("skills.conductor.verified.execute_verified", side_effect=AssertionError("executor")), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(pilot.main(["--output", str(output)]), 0)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["mode"], "preview")
            self.assertFalse(report["complete"])
            self.assertEqual([case["status"] for case in report["cases"]], ["not_executed", "not_executed"])
            self.assertTrue(all(value is None for value in report["usage"].values()))
            self.assertEqual(list(root.iterdir()), [output])

    def test_new_output_and_bounded_flags_guard_dispatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "existing.json"
            output.write_text("keep exactly\n", encoding="utf-8")
            dangling = Path(temporary) / "dangling.json"
            dangling.symlink_to("missing-target.json")
            with patch.object(pilot, "run_pilot", side_effect=AssertionError("ran before guard")), \
                    contextlib.redirect_stderr(io.StringIO()):
                for args in ([], ["--run", "--output", str(output)], ["--output", str(output)],
                             ["--run", "--output", str(dangling)], ["--output", str(dangling)],
                             ["--output", "unused", "--timeout", "31"]):
                    with self.subTest(args=args), self.assertRaises(SystemExit) as raised:
                        pilot.main(args)
                    self.assertEqual(raised.exception.code, 2)
            self.assertEqual(output.read_text(encoding="utf-8"), "keep exactly\n")
            self.assertTrue(dangling.is_symlink())
            self.assertFalse((Path(temporary) / "missing-target.json").exists())
            with self.assertRaises(FileExistsError):
                pilot.save_new(output, {"changed": True})
            for kwargs in ({"run": 1}, {"timeout": True}, {"timeout": 31}, {"timeout": 0}):
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                    pilot.run_pilot(Path(temporary), **kwargs)

    def test_existing_executor_confirmation_still_guards_fixed_worker(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = pilot.build_project(root, {}, "shared")
            with patch("subprocess.run", side_effect=AssertionError("unconfirmed dispatch")):
                report = execute_verified(plan, cwd=str(root), confirm=False)
            self.assertFalse(report["complete"])
            self.assertTrue(all(row["status"] == "blocked" and row["started"] is False
                                for row in report["results"]))
            self.assertEqual(set(pilot.counters(root).values()), {0})

    def test_worker_source_drift_blocks_before_default_runner(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = pilot.build_project(root, {}, "shared")
            with (root / "worker.py").open("a", encoding="utf-8") as stream:
                stream.write("\nraise SystemExit('modified worker')\n")
            with patch("subprocess.run", side_effect=AssertionError("drift dispatched")):
                report = execute_verified(plan, cwd=str(root), confirm=True, timeout=5)
            self.assertFalse(report["complete"])
            self.assertTrue(all(row["status"] == "blocked" and row["started"] is False
                                for row in report["results"]))
            self.assertEqual(set(pilot.counters(root).values()), {0})

    def test_equal_but_wrong_business_result_does_not_pass_output_oracle(self):
        bad_worker = pilot.WORKER.replace('sum(row["value"] for row in rows)', "0")
        self.assertNotEqual(bad_worker, pilot.WORKER)
        with tempfile.TemporaryDirectory() as temporary, patch.object(pilot, "WORKER", bad_worker):
            root = Path(temporary)
            plan = pilot.build_project(root, {}, "shared")
            report = execute_verified(plan, cwd=str(root), confirm=True, timeout=5)
            self.assertFalse(report["complete"])
            summary = next(row for row in report["results"] if row["id"] == "summary-shared")
            self.assertEqual(summary["exit_code"], 0)
            self.assertEqual(summary["status"], "unverified")
            self.assertEqual(json.loads((root / "summary.json").read_text(encoding="utf-8")),
                             {"count": 3, "total": 0})
            self.assertEqual(json.loads((root / "index.json").read_text(encoding="utf-8")),
                             pilot.EXPECTED["index.json"])

    def test_real_both_plans_verify_same_outputs_prepared_twice_versus_once(self):
        report = pilot.run_pilot(Path(__file__).resolve().parents[1], run=True, timeout=5)
        self.assertTrue(report["complete"], report["failures"])
        self.assertTrue(all(report["checks"].values()))
        separate, shared = report["cases"]
        self.assertEqual([case["preparation_count"] for case in report["cases"]], [2, 1])
        self.assertTrue(all(case["execution"]["complete"] for case in report["cases"]))
        self.assertEqual(separate["output_sha256"], shared["output_sha256"])
        self.assertEqual(set(separate["output_sha256"]), set(pilot.EXPECTED))
        self.assertTrue(all(case["handoff_input_digest"] == report["comparison_input_digest"]
                            and case["handoff_execution_authorized"] is False for case in report["cases"]))
        self.assertEqual([len(case["execution"]["results"]) for case in report["cases"]], [4, 3])
        self.assertTrue(pilot.sources_match(Path(__file__).resolve().parents[1], report["source_hashes"]))
        self.assertIsNone(report["synergy_analysis"]["selected_candidate_id"])
        self.assertEqual(report["synergy_analysis"]["opportunities"][0]["status"], "compared")
        self.assertEqual(report["active_operations"], [])
        self.assertTrue(report["temporary_projects_deleted"])
        self.assertIsNone(report["gain_claim"])
        self.assertTrue(all(value is None for key, value in report["usage"].items() if key != "elapsed_wall_s"))
        self.assertLess(len(json.dumps(report).encode("utf-8")), 90_000)

    def test_case_failure_retains_both_methods_and_other_method_evidence(self):
        bad_worker = pilot.WORKER.replace('if stage in prepares:', 'if stage == "prep-a":\n    raise SystemExit(7)\nif stage in prepares:')
        with patch.object(pilot, "WORKER", bad_worker):
            report = pilot.run_pilot(Path(__file__).resolve().parents[1], run=True, timeout=5)
        self.assertFalse(report["complete"])
        self.assertTrue(report["failures"])
        separate, shared = report["cases"]
        self.assertFalse(separate["execution"]["complete"])
        self.assertTrue(shared["execution"]["complete"])
        self.assertEqual(next(row for row in separate["execution"]["results"] if row["id"] == "prep-a")["exit_code"], 7)
        self.assertTrue(report["temporary_projects_deleted"])

    def test_setup_errors_are_retained_and_temporary_projects_removed(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = pilot.run_pilot(Path(temporary), run=True, timeout=5)
        self.assertFalse(report["complete"])
        self.assertEqual(report["failures"][0]["reason"], "FileNotFoundError")
        self.assertEqual([case["status"] for case in report["cases"]], ["not_executed", "not_executed"])
        self.assertTrue(report["temporary_projects_deleted"])


if __name__ == "__main__":
    unittest.main()
