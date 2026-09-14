"""Confrontation completeness and counter-report compatibility in fixtures."""

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from skills.cardinal.scripts.cardinal_confront import main


class CardinalTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.blue, self.red = self.root / "blue", self.root / "red"
        self.red.mkdir()

    def write(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    def inputs(self, canonical=False, findings=False):
        for path in ("audit/audit-report.json", "fix-report.json",
                     "optimize/optimization-plan.json"):
            self.write(self.blue / path, {"source": "controlled fixture"})
        items = [{"f": "fixture.py:1", "d": "fixture finding"}] if findings else []
        self.write(self.red / "counter-audit.json",
                   {"false_negatives": items, "underestimated": items})
        self.write(self.red / "counter-fix.json",
                   {"regressions": items,
                    "incomplete_fixes" if canonical else "incomplete": items})
        self.write(self.red / "counter-optim.json",
                   {"over_optimizations": items,
                    "wrongly_excluded_skills" if canonical else "wrongly_excluded": items})

    def run_report(self):
        with contextlib.redirect_stdout(io.StringIO()) as output, \
             contextlib.redirect_stderr(io.StringIO()) as errors:
            code = main([str(self.blue), str(self.red)])
        return code, output.getvalue(), errors.getvalue()

    def test_missing_inputs_preserve_prior_report_and_do_not_claim_reliability(self):
        previous = self.red / "confrontation.json"
        previous.write_text("prior evidence", encoding="utf-8")
        code, output, errors = self.run_report()
        self.assertEqual(code, 2)
        self.assertNotIn("FIABLE", output)
        self.assertIn("incomplete", errors)
        self.assertEqual(previous.read_text(encoding="utf-8"), "prior evidence")

    def test_prompt_aliases_and_canonical_fields_contribute_to_score(self):
        for canonical in (False, True):
            with self.subTest(canonical=canonical):
                self.inputs(canonical=canonical, findings=True)
                self.assertEqual(self.run_report()[0], 0)
                report = json.loads((self.red / "confrontation.json").read_text(encoding="utf-8"))
                self.assertEqual(report["blue_score"], 71)
                self.assertEqual(report["red_findings"], 6)

    def test_explicit_empty_finding_lists_remain_valid_inputs(self):
        self.inputs()
        self.assertEqual(self.run_report()[0], 0)
        report = json.loads((self.red / "confrontation.json").read_text(encoding="utf-8"))
        self.assertEqual(report["red_findings"], 0)
        self.assertEqual(report["blue_score"], 100)  # report-derived score only

    def test_invalid_reports_and_missing_finding_fields_do_not_write(self):
        self.inputs()
        target = self.red / "counter-fix.json"
        for value in ("{", "[]", "{}", '{"regressions": []}',
                      '{"regressions": "none", "incomplete": []}',
                      '{"regressions": [1], "incomplete": []}'):
            with self.subTest(value=value):
                target.write_text(value, encoding="utf-8")
                self.assertEqual(self.run_report()[0], 2)
                self.assertFalse((self.red / "confrontation.json").exists())

    def test_conflicting_aliases_do_not_hide_findings(self):
        self.inputs()
        self.write(self.red / "counter-fix.json",
                   {"regressions": [], "incomplete": [{"d": "missed"}], "incomplete_fixes": []})
        self.assertEqual(self.run_report()[0], 2)
        self.assertFalse((self.red / "confrontation.json").exists())

    def test_script_propagates_incomplete_exit_status(self):
        script = Path(__file__).parent / "scripts" / "cardinal_confront.py"
        result = subprocess.run([sys.executable, str(script), str(self.blue), str(self.red)],
                                capture_output=True, text=True, encoding="utf-8", timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertFalse((self.red / "confrontation.json").exists())


def main_tests():
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(CardinalTests))
    failed = len(result.failures) + len(result.errors)
    print(f"RESULT: {result.testsRun - failed} passed, {failed} failed")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main_tests())
