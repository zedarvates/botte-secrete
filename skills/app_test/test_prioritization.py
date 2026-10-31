"""Scheduling behavior against explicit observed history, not implementation mirrors."""

import unittest

from skills.app_test.prioritization import (
    append_observations, command_fingerprint, prioritize_checks,
)


class PriorityTests(unittest.TestCase):
    def row(self, label, command, duration, outcome):
        return {"label": label, "command_sha256": command_fingerprint(command),
                "duration_ms": duration, "outcome": outcome}

    def test_failing_fast_check_moves_before_slow_pass_without_omission(self):
        checks = [("slow", ["slow"]), ("unseen", ["new"]), ("bad", ["bad"])]
        history = {"schema": "parcimonia.test-history/v1", "runs": [
            self.row("slow", ["slow"], 10000, "passed"),
            self.row("bad", ["bad"], 5, "failed")]}
        result = prioritize_checks(checks, history)
        self.assertEqual([x["label"] for x in result["ordered"]], ["bad", "unseen", "slow"])
        self.assertEqual(result["omitted"], 0)
        self.assertFalse(result["boundaries"]["execution"])

    def test_unknown_history_preserves_original_order(self):
        checks = [("b", ["b"]), ("a", ["a"])]
        result = prioritize_checks(checks, {"schema": "parcimonia.test-history/v1", "runs": []})
        self.assertEqual([x["label"] for x in result["ordered"]], ["b", "a"])

    def test_changed_command_and_incomplete_do_not_inherit_pass_evidence(self):
        checks = [("same", ["new"]), ("unavailable", ["x"])]
        history = {"schema": "parcimonia.test-history/v1", "runs": [
            self.row("same", ["old"], 100, "failed"),
            self.row("unavailable", ["x"], 1, "incomplete")]}
        result = prioritize_checks(checks, history)
        self.assertEqual([x["observations"] for x in result["ordered"]], [0, 0])

    def test_zero_duration_is_finite_and_repeatable(self):
        h = {"schema": "parcimonia.test-history/v1", "runs": [self.row("a", ["a"], 0, "failed")]}
        self.assertEqual(prioritize_checks([("a", ["a"])], h), prioritize_checks([("a", ["a"])], h))

    def test_invalid_observations_and_duplicate_labels_rejected(self):
        h = {"schema": "parcimonia.test-history/v1", "runs": []}
        for duration in (True, -1, float("nan"), float("inf"), 10**1000):
            with self.subTest(duration=duration), self.assertRaises(ValueError):
                prioritize_checks([("a", ["a"])], {**h, "runs": [self.row("a", ["a"], duration, "passed")]})
        with self.assertRaises(ValueError):
            prioritize_checks([("a", ["a"]), ("a", ["b"])], h)

    def test_retry_pass_keeps_previous_failure(self):
        h = {"schema": "parcimonia.test-history/v1", "runs": [self.row("a", ["a"], 1, "failed")]}
        updated = append_observations(h, [self.row("a", ["a"], 2, "passed")])
        result = prioritize_checks([("a", ["a"])], updated)
        self.assertEqual(result["ordered"][0]["observed_failures"], 1)
        self.assertEqual(result["ordered"][0]["observations"], 2)


if __name__ == "__main__":
    unittest.main()
