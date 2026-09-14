"""Temporary-state regressions for routing threshold proposals and persistence."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skills.auto_router import effort
from skills.control_loop import control_loop as loop


INVALID = [None, [], [0.1, 0.2, 0.3], [0.1, 0.1, 0.5, 0.8],
           [0.4, 0.3, 0.5, 0.8], [-0.1, 0.3, 0.5, 0.8], [0.1, 0.3, 0.5, 1.1],
           [False, 0.3, 0.5, 0.8], ["0.1", 0.3, 0.5, 0.8],
           [0.1, float("nan"), 0.5, 0.8], [0.1, 0.3, 0.5, float("inf")]]


class ControlEffectsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / "thresholds.json"

    def test_invalid_apply_preserves_existing_file_and_absent_parent(self):
        original = b'{"thresholds": [0.08, 0.3, 0.55, 0.8]}\n'
        self.config.write_bytes(original)
        for value in INVALID:
            for destination in (self.config, self.root / "absent" / "thresholds.json"):
                with self.subTest(value=value, destination=str(destination)), self.assertRaises(ValueError):
                    loop.apply(value, path=destination)
                self.assertEqual(self.config.read_bytes(), original)
                self.assertFalse((self.root / "absent").exists())

    def test_invalid_config_falls_back_without_rewriting_it(self):
        documents = [[], None, "text", {}, *({"thresholds": value} for value in INVALID)]
        with patch.object(effort, "_THRESHOLDS_PATH", self.config):
            for document in documents:
                with self.subTest(document=document):
                    self.config.write_text(json.dumps(document), encoding="utf-8")
                    before = self.config.read_bytes()
                    self.assertEqual(effort.load_thresholds(), effort.DEFAULT_THRESHOLDS)
                    self.assertEqual(self.config.read_bytes(), before)

    def test_failed_atomic_replace_retains_previous_thresholds(self):
        loop.apply(list(effort.DEFAULT_THRESHOLDS), path=self.config)
        before = self.config.read_bytes()
        with patch("skills.atomic_json.Path.replace", side_effect=OSError("fixture replace failure")):
            with self.assertRaises(OSError):
                loop.apply([0.08, 0.4, 0.55, 0.8], path=self.config)
        self.assertEqual(self.config.read_bytes(), before)
        self.assertEqual(list(self.root.glob(".*.tmp")), [])

    def test_valid_apply_and_reset_change_the_live_reader(self):
        with patch.object(effort, "_THRESHOLDS_PATH", self.config):
            self.assertEqual(effort._tier_for(0.35).name, "CHEAP")
            self.assertEqual(loop.apply([0.08, 0.4, 0.55, 0.8], path=self.config), self.config)
            self.assertEqual(effort._tier_for(0.35).name, "LOCAL")
            loop.reset_thresholds(path=self.config)
            self.assertEqual(effort._tier_for(0.35).name, "CHEAP")

    def test_narrow_spacing_does_not_produce_unordered_thresholds(self):
        original = [0.48, 0.49, 0.50, 0.7]
        proposal = loop.adapt({"samples": 20, "success_rate": 1.0, "escalation_rate": 0.0}, thresholds=original)
        self.assertFalse(proposal["changed"])
        self.assertEqual(proposal["thresholds"], original)

    def test_invalid_explicit_proposal_inputs_are_not_silently_defaulted(self):
        with patch.object(loop, "load_thresholds", return_value=list(effort.DEFAULT_THRESHOLDS)):
            for thresholds in ([], [0.4, 0.3, 0.5, 0.8]):
                with self.subTest(thresholds=thresholds), self.assertRaises(ValueError):
                    loop.adapt({"samples": 20}, thresholds=thresholds)

    def test_proposal_does_not_apply_or_modify_its_evidence(self):
        ledger = self.root / "ledger.jsonl"
        for _ in range(12):
            loop.record(task="fixture", mode="local", success=True, path=ledger)
        loop.apply(list(effort.DEFAULT_THRESHOLDS), path=self.config)
        before_config, before_ledger = self.config.read_bytes(), ledger.read_bytes()
        proposal = loop.adapt(loop.analyze(loop.load(ledger)), thresholds=list(effort.DEFAULT_THRESHOLDS))
        self.assertTrue(proposal["changed"])
        self.assertEqual(self.config.read_bytes(), before_config)
        self.assertEqual(ledger.read_bytes(), before_ledger)


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ControlEffectsTests))
    failed = len({getattr(test, "test_case", test).id() for test, _ in result.failures + result.errors})
    print(f"RESULT: {result.testsRun - failed} passed, {failed} failed")
    raise SystemExit(0 if result.wasSuccessful() else 1)
