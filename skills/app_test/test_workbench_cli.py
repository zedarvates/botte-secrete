"""Actual local command-line integration, with authored fixtures only."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class WorkbenchCliTests(unittest.TestCase):
    def call(self, *args):
        proc = subprocess.run([sys.executable, "-m", "skills.app_test.workbench", *map(str, args)],
                              cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30)
        return proc.returncode, json.loads(proc.stdout)

    def write(self, root, name, value):
        path = root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_reduce_real_json_oracle_and_retained_process_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            items = self.write(root, "items.json", [1, 7, 2, 13, 4])
            script = root / "oracle.py"
            script.write_text('import json,sys\nx=json.load(sys.stdin)\nprint(json.dumps({"status":"failed","failure_fingerprint":"PAIR"} if 7 in x and 13 in x else {"status":"passed"}))\n', encoding="utf-8")
            command = self.write(root, "command.json", [sys.executable, str(script)])
            code, report = self.call("reduce", "--input", items, "--command-file", command)
            self.assertEqual(code, 0)
            self.assertTrue(report["failure_preserved"])
            self.assertEqual(report["reduced_items"], [7, 13])
            self.assertEqual(json.loads(items.read_text(encoding="utf-8")), [1, 7, 2, 13, 4])
            observed = report["process_adapter"]["observations"]
            self.assertTrue(observed)
            self.assertTrue(all(row["exit"] == 0 and len(row["command_sha256"]) == 64 for row in observed))

    def test_triage_actual_alternating_child_never_hides_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "oracle.py"
            script.write_text('import json,sys\nx=json.load(sys.stdin)\nprint(json.dumps({"status":"failed","failure_signature":"SAME"} if x["attempt"]%2==0 else {"status":"passed"}))\n', encoding="utf-8")
            command = self.write(root, "command.json", [sys.executable, str(script)])
            code, report = self.call("triage", "--command-file", command, "--attempts", 3)
            self.assertEqual(code, 1)
            self.assertEqual(report["classification"], "intermittent_observed")
            self.assertTrue(report["failure_ever_reported"])
            self.assertEqual(len(report["process_adapter"]["observations"]), 3)

    def test_missing_command_and_no_json_are_incomplete(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            command = self.write(root, "command.json", ["/definitely-missing-workbench-command"])
            code, report = self.call("triage", "--command-file", command)
            self.assertEqual(code, 2)
            self.assertEqual(report["classification"], "environment_unavailable")
            command = self.write(root, "command.json", [sys.executable, "-c", "print('crashed')"])
            items = self.write(root, "items.json", [1])
            code, report = self.call("reduce", "--command-file", command, "--input", items)
            self.assertEqual(code, 2)
            self.assertFalse(report["failure_preserved"])

    def test_model_replay_and_priority_remain_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = self.write(root, "model.json", {"scope":"demo", "initial_state":"home",
                "states":{"home":{"actions":{"go":"done"}},"done":{"actions":{},"terminal":True}}})
            actions = self.write(root, "actions.json", ["go"])
            code, report = self.call("explore", "--model", model, "--scope", "demo", "--actions", actions)
            self.assertEqual(code, 0)
            self.assertEqual(report["adapter_kind"], "model_replay")
            self.assertFalse(report["boundaries"]["graphical_qualification"])
            priority = self.write(root, "priority.json", {"checks":[{"label":"a","command":["a"]}]})
            code, report = self.call("prioritize", "--input", priority)
            self.assertEqual(code, 0)
            self.assertEqual(report["omitted"], 0)

    def test_real_mutation_campaign_keeps_original_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "subject.py"
            original = "# original header\ndef enabled(x):\n    return x >= 3\n"
            source.write_text(original, encoding="utf-8")
            (root / "test_subject.py").write_text(
                'import unittest\nfrom subject import enabled\nclass T(unittest.TestCase):\n'
                '    def test_boundary(self):\n        self.assertTrue(enabled(3))\n', encoding="utf-8")
            code, report = self.call("mutate", "--project", root, "--source", "subject.py",
                                     "--tests", "test_subject.py", "--max-mutants", 2)
            self.assertEqual(code, 0, report)
            self.assertEqual(report["counts"]["killed"], 2)
            self.assertEqual(source.read_text(encoding="utf-8"), original)

    def test_unavailable_conformance_is_not_success(self):
        code, report = self.call("conformance", "--cloud-root", "/definitely-missing-cloud-source")
        self.assertEqual(code, 2)
        self.assertFalse(report["passed"])


if __name__ == "__main__":
    unittest.main()
