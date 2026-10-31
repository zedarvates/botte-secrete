"""Repeated-run triage contracts; no GUI or model is exercised."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess
import sys
import unittest

from skills.app_test.flaky import triage_failures


class FlakyTriageTests(unittest.TestCase):
    def series(self, values, **kwargs):
        return triage_failures(lambda index, seed, digest: values[index],
                               max_attempts=len(values), **kwargs)

    def test_failure_then_pass_never_erases_failure(self):
        report = self.series([{"status": "failed", "failure_signature": "assert:x"},
                              {"status": "passed"}, {"status": "passed"}])
        self.assertEqual(report["classification"], "intermittent_observed")
        self.assertTrue(report["failure_ever_reported"])
        self.assertEqual(report["counts"], {"passed": 2, "failed": 1,
                                           "incomplete": 0, "not_run": 0})
        self.assertEqual(report["attempts"][0]["failure_signature"], "assert:x")
        self.assertEqual(report["failure_groups"][0]["attempt_indices"], [0])

    def test_same_signed_failures_are_reproduced_in_observed_series(self):
        report = self.series([{"status": "failed", "failure_signature": "same"}] * 3)
        self.assertEqual(report["classification"], "reproduced_failure")
        self.assertFalse(report["boundaries"]["general_reliability_established"])
        self.assertFalse(report["boundaries"]["cause_diagnosed"])

    def test_different_failure_signatures_are_distinct(self):
        report = self.series([{"status": "failed", "failure_signature": "one"},
                              {"status": "failed", "failure_signature": "two"}])
        self.assertEqual(report["classification"], "varying_failures_observed")
        self.assertEqual(len(report["failure_groups"]), 2)

    def test_single_failure_or_unsigned_failures_are_insufficient(self):
        for values in ([{"status": "failed", "failure_signature": "x"}],
                       [{"status": "failed"}] * 3):
            with self.subTest(values=values):
                report = self.series(values)
                self.assertEqual(report["classification"], "insufficient_evidence")
                self.assertTrue(report["failure_ever_reported"])

    def test_all_passes_are_not_claimed_to_prove_reliability(self):
        report = self.series([{"status": "passed"}] * 3)
        self.assertEqual(report["classification"], "no_failure_observed")
        self.assertFalse(report["failure_ever_reported"])
        self.assertFalse(report["boundaries"]["general_reliability_established"])
        self.assertNotIn("passed", report)

    def test_environment_unavailable_and_partial_evidence_remain_distinct(self):
        unavailable = self.series([{"status": "not_run", "reason": "runner_missing"}] * 2)
        self.assertEqual(unavailable["classification"], "environment_unavailable")
        for values in ([{"status": "incomplete"}] * 2,
                       [{"status": "passed"}, {"status": "not_run"}],
                       [{"status": "failed", "failure_signature": "x"},
                        {"status": "incomplete"}]):
            with self.subTest(values=values):
                self.assertEqual(self.series(values)["classification"], "insufficient_evidence")

    def test_seed_and_context_fingerprint_are_unchanged_across_attempts(self):
        calls = []

        def runner(index, seed, digest):
            calls.append((index, seed, digest))
            return {"status": "passed", "context_sha256": digest}

        report = triage_failures(runner, seed=41, context={"build": "abc", "scenario": 7},
                                 max_attempts=3)
        self.assertEqual([x[0] for x in calls], [0, 1, 2])
        self.assertEqual({x[1] for x in calls}, {41})
        self.assertEqual({x[2] for x in calls}, {report["context_sha256"]})
        self.assertTrue(all(a["context_match"] for a in report["attempts"]))
        other = triage_failures(runner, seed=41, context={"scenario": 7, "build": "abc"},
                                max_attempts=1)
        self.assertEqual(report["context_sha256"], other["context_sha256"])

    def test_changed_context_does_not_contribute_false_reproduction(self):
        report = self.series([{"status": "failed", "failure_signature": "x"},
                              {"status": "failed", "failure_signature": "x",
                               "context_sha256": "another"}])
        self.assertEqual(report["classification"], "insufficient_evidence")
        self.assertEqual(report["counts"]["failed"], 1)
        self.assertEqual(report["reported_counts"]["failed"], 2)
        self.assertEqual(report["attempts"][1]["status"], "incomplete")
        self.assertEqual(report["attempts"][1]["reported_status"], "failed")
        self.assertEqual(report["failure_groups"][0]["attempt_indices"], [0, 1])
        self.assertEqual(report["failure_groups"][0]["eligible_attempt_indices"], [0])

    def test_missing_observed_context_does_not_claim_a_match(self):
        report = self.series([{"status": "passed"}])
        self.assertIsNone(report["attempts"][0]["context_match"])

    def test_invalid_adapter_results_and_exceptions_are_incomplete(self):
        for value in (None, [], {"status": "success"}, {"status": []},
                      {"status": "failed", "failure_signature": {}},
                      {"status": "failed", "failure_signature": "\ud800"},
                      {"status": "passed", "reason": "\ud800"}):
            with self.subTest(value=value):
                report = self.series([value])
                self.assertEqual(report["classification"], "insufficient_evidence")
                self.assertEqual(report["attempts"][0]["status"], "incomplete")

        def runner(*args):
            raise TimeoutError("private details must not appear")

        report = triage_failures(runner, max_attempts=2)
        self.assertEqual(report["counts"]["incomplete"], 2)
        self.assertNotIn("private details", json.dumps(report))
        self.assertEqual(report["attempts"][0]["error_type"], "TimeoutError")

    def test_zero_time_budget_does_not_run_adapter(self):
        calls = []
        report = triage_failures(lambda *args: calls.append(args), max_seconds=0)
        self.assertEqual(calls, [])
        self.assertEqual(report["attempts"], [])
        self.assertEqual(report["stop_reason"], "time_budget")
        self.assertEqual(report["classification"], "insufficient_evidence")

    def test_time_budget_overrun_is_reported_without_claiming_interruption(self):
        ticks = iter([0.0, 0.0, 2.0])
        report = triage_failures(lambda *args: {"status": "failed", "failure_signature": "x"},
                                 max_attempts=10, max_seconds=1, clock=lambda: next(ticks))
        self.assertEqual(len(report["attempts"]), 1)
        self.assertEqual(report["attempt_count"], 1)
        self.assertEqual(report["elapsed_ms"], 2000)
        self.assertTrue(report["budget"]["observed_overrun"])
        self.assertEqual(report["attempts"][0]["elapsed_ms"], 2000)
        self.assertEqual(report["budget"]["time_budget_kind"], "cooperative_between_calls")

    def test_large_text_is_bounded_but_full_signatures_remain_distinct(self):
        common = "x" * 700
        report = self.series([{"status": "failed", "failure_signature": common + "a",
                               "reason": "r" * 2000},
                              {"status": "failed", "failure_signature": common + "b"}])
        self.assertEqual(report["classification"], "varying_failures_observed")
        self.assertEqual(len(report["attempts"][0]["failure_signature"]), 512)
        self.assertEqual(len(report["attempts"][0]["reason"]), 1024)
        self.assertTrue(report["attempts"][0]["signature_truncated"])
        self.assertTrue(report["attempts"][0]["reason_truncated"])
        self.assertEqual(len(report["failure_groups"]), 2)

    def test_invalid_inputs_are_rejected_before_runner(self):
        for kwargs in ({"seed": True}, {"seed": -1}, {"seed": 1 << 32},
                       {"max_attempts": False}, {"max_attempts": 0}, {"max_attempts": 101},
                       {"max_seconds": True}, {"max_seconds": -1}, {"max_seconds": 301},
                       {"max_seconds": float("nan")}, {"max_seconds": float("inf")},
                       {"max_seconds": 10 ** 1000},
                       {"context": []}, {"context": {"x": float("nan")}},
                       {"context": {"x": "\ud800"}}, {"context": {"x": "z" * 65536}}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    triage_failures(lambda *args: self.fail("must not run"), **kwargs)

    def test_real_subprocess_fixed_and_alternating_failures(self):
        for alternating in (False, True):
            with self.subTest(alternating=alternating):
                def runner(index, seed, digest):
                    code = "import sys; sys.exit(int(sys.argv[1]))"
                    exit_code = int(not alternating or index % 2 == 0)
                    proc = subprocess.run([sys.executable, "-I", "-c", code, str(exit_code)],
                                          capture_output=True, timeout=5, check=False)
                    return {"status": "failed" if proc.returncode else "passed",
                            "failure_signature": "exit:1" if proc.returncode else None,
                            "context_sha256": digest}

                report = triage_failures(runner, seed=7, context={"fixture": "exit"},
                                         max_attempts=4, max_seconds=10)
                self.assertEqual(report["classification"], "intermittent_observed"
                                 if alternating else "reproduced_failure")
                self.assertEqual(len(report["attempts"]), 4)
                self.assertTrue(report["failure_ever_reported"])

    def test_sources_parse_on_python_310(self):
        for path in (Path(__file__), Path(__file__).with_name("flaky.py")):
            ast.parse(path.read_text(encoding="utf-8"), feature_version=(3, 10))


if __name__ == "__main__":
    unittest.main()
