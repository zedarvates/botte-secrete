"""Behavioral checks for bounded reproduction reduction; no GUI is launched."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import unittest
from unittest.mock import patch

from skills.app_test.reducer import reduce_reproduction


def failed(fingerprint="reconnect/KeyError/session"):
    return {"status": "failed", "failure_fingerprint": fingerprint}


class ReducerTests(unittest.TestCase):
    def test_real_ordered_reproduction_is_reduced_and_rechecked(self):
        calls = []

        def oracle(actions):
            calls.append(copy.deepcopy(actions))
            connected = False
            for action in actions:
                if action == "connect":
                    connected = True
                if action == "reconnect" and connected:
                    return failed()
            return {"status": "passed"}

        items = ["draw", "connect", "sleep", "tick", "reconnect", "draw"]
        result = reduce_reproduction(items, oracle)
        self.assertEqual(result["status"], "reduced")
        self.assertEqual(result["reduced_items"], ["connect", "reconnect"])
        self.assertTrue(result["failure_preserved"])
        self.assertEqual(result["minimality"], "one_deletion_minimal_observed")
        self.assertEqual(calls[-1], result["reduced_items"])
        self.assertEqual(result["calls"], len(calls))
        self.assertFalse(result["boundaries"]["global_minimum"])
        self.assertEqual(result["removed_count"], 4)

    def test_empty_input_failure_is_retained(self):
        result = reduce_reproduction(["irrelevant"], lambda _: failed())
        self.assertEqual(result["reduced_items"], [])
        self.assertEqual(result["stop_reason"], "empty_failure")
        self.assertTrue(result["failure_preserved"])
        self.assertEqual(result["final_verification"], failed())

    def test_already_empty_witness_is_rechecked(self):
        result = reduce_reproduction([], lambda _: failed())
        self.assertEqual(result["status"], "unchanged")
        self.assertEqual(result["calls"], 2)
        self.assertEqual(result["minimality"], "one_deletion_minimal_observed")

    def test_one_call_budget_never_runs_a_second_call(self):
        seen = []
        result = reduce_reproduction([1, 2], lambda x: seen.append(x) or failed(), max_calls=1)
        self.assertEqual(len(seen), 1)
        self.assertEqual(result["calls"], 1)
        self.assertEqual(result["status"], "inconclusive")
        self.assertEqual(result["stop_reason"], "call_budget")
        self.assertIsNone(result["final_verification"])
        self.assertFalse(result["failure_preserved"])

    def test_call_budget_reserves_final_verification(self):
        result = reduce_reproduction([1, 2, 3],
                                     lambda x: failed() if x else {"status": "passed"},
                                     max_calls=3)
        self.assertEqual(result["calls"], 3)
        self.assertEqual(result["status"], "unchanged")
        self.assertEqual(result["stop_reason"], "call_budget")
        self.assertTrue(result["failure_preserved"])
        self.assertEqual(result["minimality"], "not_established")

    def test_different_failure_is_never_accepted(self):
        result = reduce_reproduction(["required", "context"],
                                     lambda x: failed("target") if len(x) == 2 else failed("other"))
        self.assertEqual(result["reduced_items"], ["required", "context"])
        self.assertEqual(result["failure_fingerprint"], "target")
        self.assertEqual(result["status"], "unchanged")

    def test_expected_fingerprint_must_match_baseline(self):
        result = reduce_reproduction([1], lambda _: failed("unexpected"),
                                     expected_fingerprint="required")
        self.assertEqual(result["status"], "not_reproduced")
        self.assertEqual(result["stop_reason"], "baseline_failure_mismatch")
        self.assertEqual(result["calls"], 1)

    def test_baseline_requires_an_explicit_failure_fingerprint(self):
        cases = [({"status": "passed"}, "not_reproduced"),
                 ({"status": "failed"}, "inconclusive"),
                 ({"status": "failed", "failure_fingerprint": ""}, "inconclusive"),
                 ({"status": "inconclusive"}, "inconclusive"),
                 ({"status": "timeout"}, "inconclusive"),
                 ({"status": "error"}, "inconclusive"),
                 ({"status": ["failed"]}, "inconclusive"),
                 (True, "inconclusive")]
        for observation, status in cases:
            with self.subTest(observation=observation):
                result = reduce_reproduction([1], lambda _: observation)
                self.assertEqual(result["status"], status)
                self.assertFalse(result["failure_preserved"])
                self.assertEqual(result["calls"], 1)

    def test_oracle_exceptions_are_separate_and_do_not_leak_messages(self):
        for error, expected in [(RuntimeError("private credential"), "error"),
                                (TimeoutError("private command"), "timeout"),
                                (subprocess.TimeoutExpired("private command", 1), "timeout")]:
            with self.subTest(error=type(error).__name__):
                def oracle(_):
                    raise error
                result = reduce_reproduction([1], oracle)
                self.assertEqual(result["trace"][0]["status"], expected)
                self.assertNotIn("private", json.dumps(result))

    def test_cooperative_deadline_discards_late_result(self):
        now = [0.0]

        def oracle(_):
            now[0] += 2.0
            return failed()

        with patch("skills.app_test.reducer.time.monotonic", side_effect=lambda: now[0]):
            result = reduce_reproduction([1], oracle, max_seconds=1)
        self.assertEqual(result["calls"], 1)
        self.assertEqual(result["stop_reason"], "time_budget")
        self.assertEqual(result["trace"][0]["status"], "timeout")
        self.assertFalse(result["failure_preserved"])

    def test_deadline_stops_before_new_callback(self):
        now = [0.0]
        seen = []

        def oracle(candidate):
            seen.append(candidate)
            if len(seen) == 2:
                now[0] = 2
                return {"status": "passed"}
            return failed()

        with patch("skills.app_test.reducer.time.monotonic", side_effect=lambda: now[0]):
            result = reduce_reproduction([1, 2], oracle, max_seconds=1)
        self.assertEqual(len(seen), 2)
        self.assertEqual(result["stop_reason"], "time_budget")
        self.assertEqual(result["status"], "inconclusive")

    def test_final_recheck_can_disprove_the_failure(self):
        outcomes = iter([failed(), {"status": "passed"}])
        result = reduce_reproduction([1], lambda _: next(outcomes), max_calls=2)
        self.assertEqual(result["status"], "inconclusive")
        self.assertFalse(result["failure_preserved"])
        self.assertEqual(result["final_verification"]["status"], "passed")

    def test_unknown_deletions_do_not_establish_minimality(self):
        result = reduce_reproduction([1, 2], lambda x: failed() if len(x) == 2
                                     else {"status": "inconclusive"})
        self.assertEqual(result["status"], "unchanged")
        self.assertEqual(result["minimality"], "not_established")
        self.assertGreater(result["outcomes"]["inconclusive"], 0)

    def test_input_is_snapshot_and_oracle_mutation_is_not_evidence(self):
        items = [{"steps": [1, 2]}]
        original = copy.deepcopy(items)

        def oracle(candidate):
            candidate[0]["steps"].append(3)
            return failed()

        result = reduce_reproduction(items, oracle)
        self.assertEqual(items, original)
        self.assertEqual(result["status"], "inconclusive")
        self.assertEqual(result["trace"][0]["reason"], "oracle_mutated_candidate")
        canonical = json.dumps(original, ensure_ascii=False, allow_nan=False,
                               sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.assertEqual(result["original_sha256"], hashlib.sha256(canonical).hexdigest())

    def test_invalid_or_excessive_inputs_do_not_call_oracle(self):
        cycle = []
        cycle.append(cycle)
        invalid = [None, (), [float("nan")], [float("inf")], [{1: "coercion"}],
                   [object()], cycle, ["x" * 20], [2 ** 3401]]
        for items in invalid:
            with self.subTest(items_type=type(items).__name__):
                with self.assertRaises(ValueError):
                    reduce_reproduction(items, lambda _: self.fail("called"), max_input_bytes=10)
        with self.assertRaises(ValueError):
            reduce_reproduction([1, 2], lambda _: self.fail("called"), max_items=1)

    def test_configuration_and_fingerprint_limits(self):
        for kwargs in [{"max_calls": 0}, {"max_calls": True}, {"max_calls": 513},
                       {"max_seconds": 0}, {"max_seconds": True},
                       {"max_seconds": float("inf")}, {"max_items": 0},
                       {"max_input_bytes": 0}, {"expected_fingerprint": ""},
                       {"expected_fingerprint": "é" * 513}]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                reduce_reproduction([1], lambda _: self.fail("called"), **kwargs)

    def test_structural_unicode_and_trace_fields_are_bounded(self):
        deep = []
        for _ in range(34):
            deep = [deep]
        for items in [deep, ["\ud800"], [[0] * 20001]]:
            with self.subTest(kind=type(items).__name__), self.assertRaises(ValueError):
                reduce_reproduction(items, lambda _: self.fail("called"))
        result = reduce_reproduction(["payload"], lambda _: failed("x" * 1024))
        self.assertEqual(result["failure_fingerprint"], "x" * 1024)
        self.assertNotIn("failure_fingerprint", result["trace"][0])
        self.assertEqual(len(result["trace"][0]["failure_fingerprint_sha256"]), 64)
        self.assertLess(len(json.dumps(result)), 6000)

    def test_actual_subprocess_oracle_can_reduce_json_input(self):
        program = ("import sys,json; x=json.load(sys.stdin); "
                   "print(json.dumps({'status':'failed','failure_fingerprint':'needle/v1'} "
                   "if 'needle' in x else {'status':'passed'}))")

        def oracle(candidate):
            process = subprocess.run([sys.executable, "-c", program],
                                     input=json.dumps(candidate), capture_output=True,
                                     text=True, encoding="utf-8", timeout=5, check=True)
            return json.loads(process.stdout)

        result = reduce_reproduction(["noise", "needle", "more noise"], oracle)
        self.assertEqual(result["reduced_items"], ["needle"])
        self.assertTrue(result["failure_preserved"])


if __name__ == "__main__":
    unittest.main()
