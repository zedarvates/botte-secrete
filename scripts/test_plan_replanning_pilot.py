"""Checks for explicit pilot scope, real checkpoint reuse and no repeated writes."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from scripts import plan_replanning_pilot as pilot
from skills.conductor.verified import execute_verified


class PlanReplanningPilotTests(unittest.TestCase):
    def test_default_preview_writes_only_requested_report_without_subprocess(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "preview.json"
            with patch("subprocess.run", side_effect=AssertionError("preview dispatched")), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(pilot.main(["--output", str(output)]), 0)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["mode"], "preview")
            self.assertFalse(report["complete"])
            self.assertEqual(report["phases"], [])
            self.assertEqual(report["usage"]["elapsed_wall_s"], None)
            self.assertEqual(list(root.iterdir()), [output])

    def test_output_is_mandatory_and_existing_file_blocks_before_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "existing.json"
            output.write_text("keep exactly\n", encoding="utf-8")
            with patch.object(pilot, "run_pilot", side_effect=AssertionError("ran before guard")), \
                    contextlib.redirect_stderr(io.StringIO()):
                for args in ([], ["--run", "--output", str(output)],
                             ["--output", str(output)], ["--output", "unused", "--timeout", "31"]):
                    with self.subTest(args=args), self.assertRaises(SystemExit) as raised:
                        pilot.main(args)
                    self.assertEqual(raised.exception.code, 2)
            self.assertEqual(output.read_text(encoding="utf-8"), "keep exactly\n")

    def test_explicit_confirmation_and_strict_pilot_flags_guard_dispatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = pilot.build_project(root, {})
            with patch("subprocess.run", side_effect=AssertionError("unconfirmed dispatch")):
                report = execute_verified(plan, cwd=str(root), confirm=False, checkpoint=pilot.CHECKPOINT)
            self.assertEqual([row["status"] for row in report["results"]], ["blocked", "blocked"])
            self.assertTrue(all(row["started"] is False for row in report["results"]))
            self.assertEqual(pilot.counters(root), {"stage-a": 0, "stage-b": 0})
            for kwargs in ({"run": 1}, {"timeout": True}, {"timeout": 31}, {"timeout": 0}):
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                    pilot.run_pilot(root, **kwargs)

    def test_worker_source_drift_blocks_real_default_runner(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = pilot.build_project(root, {})
            with (root / "worker.py").open("a", encoding="utf-8") as stream:
                stream.write("\nraise SystemExit('changed source')\n")
            report = execute_verified(plan, cwd=str(root), confirm=True, timeout=5,
                                      checkpoint=pilot.CHECKPOINT)
            self.assertFalse(report["complete"])
            self.assertTrue(all(row["status"] == "blocked" and row["started"] is False
                                for row in report["results"]))
            self.assertEqual(pilot.counters(root), {"stage-a": 0, "stage-b": 0})
            failed_setup = pilot.run_pilot(root, run=True, timeout=5)
            self.assertFalse(failed_setup["complete"])
            self.assertEqual(failed_setup["failures"][0]["reason"], "FileNotFoundError")
            self.assertEqual(failed_setup["phases"], [])
            self.assertTrue(failed_setup["temporary_project_deleted"])

    def test_real_resume_reuses_A_executes_B_once_and_detects_stale_A(self):
        report = pilot.run_pilot(Path(__file__).resolve().parents[1], run=True, timeout=5)
        self.assertTrue(report["complete"], report["failures"])
        self.assertEqual(len(report["phases"]), 5)
        self.assertTrue(all(report["checks"].values()))
        first, reviewed, resumed, stale_review, stale = report["phases"][0], report["phases"][1], \
            report["phases"][2], report["phases"][3], report["phases"][4]
        self.assertEqual(first["counters"], {"stage-a": 1, "stage-b": 0})
        self.assertEqual(resumed["counters"], {"stage-a": 1, "stage-b": 1})
        self.assertEqual(stale["counters"], resumed["counters"])
        self.assertEqual(reviewed["checkpoint_bytes_sha256_before"], reviewed["checkpoint_bytes_sha256_after"])
        self.assertEqual(stale_review["checkpoint_bytes_sha256_before"], stale_review["checkpoint_bytes_sha256_after"])
        self.assertTrue(resumed["execution"]["complete"])
        self.assertFalse(stale["execution"]["complete"])
        self.assertEqual([row["status"] for row in stale["execution"]["results"]], ["stale", "stale"])
        self.assertEqual(report["active_operations"], [])
        self.assertTrue(report["temporary_project_deleted"])
        self.assertIsNone(report["gain_claim"])
        self.assertTrue(all(value is None for key, value in report["usage"].items()
                            if key != "elapsed_wall_s"))
        self.assertLess(len(json.dumps(report).encode("utf-8")), 80_000)

    def test_changed_plan_cannot_resume_or_rewrite_original_checkpoint(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = pilot.build_project(root, {})
            initial = execute_verified(plan, cwd=str(root), confirm=True, timeout=5,
                                       checkpoint=pilot.CHECKPOINT)
            self.assertEqual(initial["results"][0]["status"], "verified")
            before = (root / pilot.CHECKPOINT).read_bytes()
            changed = deepcopy(plan)
            changed["context"] = "changed-current-plan"
            with patch("subprocess.run", side_effect=AssertionError("changed plan dispatched")):
                resumed = execute_verified(changed, cwd=str(root), confirm=True, timeout=5,
                                           checkpoint=pilot.CHECKPOINT, resume=True)
            self.assertIn("does not match", resumed["error"])
            self.assertEqual((root / pilot.CHECKPOINT).read_bytes(), before)
            self.assertEqual(pilot.counters(root), {"stage-a": 1, "stage-b": 0})


if __name__ == "__main__":
    unittest.main()
