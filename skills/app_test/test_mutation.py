"""Mutation checks: real disposable unittest projects and boundary regressions."""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

from skills.app_test.mutation import generate_mutants, run_mutation_checks, run_unittest_command


SOURCE = "def eligible(value):\n    return value >= 10\n"
STRONG_TEST = """import unittest
from subject import eligible
class SubjectTests(unittest.TestCase):
    def test_boundary(self):
        self.assertFalse(eligible(9))
        self.assertTrue(eligible(10))
        self.assertTrue(eligible(11))
"""
WEAK_TEST = """import unittest
from subject import eligible
class SubjectTests(unittest.TestCase):
    def test_happy_path(self):
        self.assertTrue(eligible(11))
"""


class MutationTests(unittest.TestCase):
    def fixture(self, directory, test=STRONG_TEST, source=SOURCE):
        root = Path(directory)
        (root / "subject.py").write_text(source, encoding="utf-8", newline="\n")
        (root / "test_subject.py").write_text(test, encoding="utf-8", newline="\n")
        return root

    def run_project(self, root, **kwargs):
        return run_mutation_checks(root, "subject.py", test_paths=["test_subject.py"],
                                   command=[sys.executable, "-m", "unittest", "test_subject"],
                                   max_mutants=1, **kwargs)

    def test_real_boundary_assertion_kills_comparison_mutant(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            result = self.run_project(root)
            self.assertEqual(result["baseline"]["status"], "passed")
            self.assertEqual(result["counts"], {"killed": 1, "survived": 0, "inconclusive": 0})
            self.assertEqual(result["mutations"][0]["mutation"]["description"], "GtE -> Gt")
            self.assertEqual(result["mutations"][0]["test_result"]["reason"], "unittest_assertion_failure")
            self.assertEqual(result["executions"], 2)
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})
            json.dumps(result, allow_nan=False)

    def test_real_weak_test_survives_and_exposes_gap(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory, WEAK_TEST)
            result = self.run_project(root)
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["counts"]["survived"], 1)
            self.assertEqual(result["counts"]["killed"], 0)

    def test_real_baseline_failure_stops_before_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory, STRONG_TEST.replace("self.assertTrue(eligible(10))", "self.assertFalse(eligible(10))"))
            result = self.run_project(root)
            self.assertEqual(result["status"], "baseline_failed")
            self.assertEqual(result["executions"], 1)
            self.assertEqual(result["mutations"], [])

    def test_real_import_failure_is_environment_inconclusive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory, "import library_that_does_not_exist\n")
            result = self.run_project(root)
            self.assertEqual(result["status"], "baseline_inconclusive")
            self.assertEqual(result["baseline"]["status"], "incomplete")
            self.assertEqual(result["mutations"], [])

    def test_real_no_tests_does_not_qualify_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory, "import unittest\n")
            self.assertEqual(self.run_project(root)["status"], "baseline_inconclusive")

    def test_real_all_skipped_does_not_qualify_baseline(self):
        test = STRONG_TEST.replace("    def test_boundary", "    @unittest.skip('fixture')\n    def test_boundary")
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory, test)
            result = self.run_project(root)
            self.assertEqual(result["baseline"]["reason"], "all_tests_skipped")
            self.assertEqual(result["mutations"], [])

    def test_real_timeout_is_inconclusive_and_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run_unittest_command([sys.executable, "-c", "import time;time.sleep(5)"], Path(directory), 0.05)
            self.assertEqual(result["status"], "incomplete")
            self.assertEqual(result["reason"], "timeout")
            self.assertLess(result["duration_ms"], 3000)

    def test_real_missing_command_is_not_run(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run_unittest_command([str(Path(directory) / "missing-command")], Path(directory), 1)
            self.assertEqual(result["status"], "not_run")
            self.assertEqual(result["reason"], "command_launch_failed")

    def test_real_unknown_nonzero_exit_is_not_called_killed(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run_unittest_command([sys.executable, "-c", "import sys;print('broken setup');sys.exit(1)"], Path(directory), 1)
            self.assertEqual(result["status"], "incomplete")

    def test_output_evidence_is_hashed_and_tailed(self):
        with tempfile.TemporaryDirectory() as directory:
            text = "a" * 10000
            result = run_unittest_command([sys.executable, "-c", "print('a'*10000)"], Path(directory), 1)
            evidence = result["stdout"]
            self.assertEqual(evidence["sha256"], hashlib.sha256((text + os.linesep).encode()).hexdigest())
            self.assertTrue(evidence["tail_truncated"])
            self.assertLessEqual(len(evidence["tail"].encode()), 4096)

    def test_output_limit_is_inconclusive(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run_unittest_command([sys.executable, "-c", "print('a'*1200000)"], Path(directory), 1)
            self.assertEqual(result["status"], "incomplete")
            self.assertEqual(result["reason"], "output_limit")
            self.assertLessEqual(len(result["stdout"]["tail"]), 4096)

    def test_mutations_are_deterministic_and_single_site(self):
        original = '"A docstring"\ndef f(x):\n    return True if x == 1 else False\n'
        first = generate_mutants(original, max_mutants=10)
        self.assertEqual(first, generate_mutants(original, max_mutants=10))
        self.assertEqual([x["kind"] for x in first], ["boolean", "comparison", "integer_plus_one", "boolean"])
        for mutation in first:
            ast.parse(mutation["source"], feature_version=(3, 10))
            self.assertTrue(mutation["source"].startswith('"A docstring"\n'))
            self.assertEqual(mutation["sha256"], hashlib.sha256(mutation["source"].encode()).hexdigest())
        self.assertIn("return False if x == 1 else False", first[0]["source"])
        self.assertIn("return True if x != 1 else False", first[1]["source"])

    def test_empty_operator_set_still_requires_passing_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory, "import unittest\nclass T(unittest.TestCase):\n def test_x(self): self.assertTrue(True)\n", '"only a docstring"\n')
            result = self.run_project(root)
            self.assertEqual(result["status"], "no_mutants")
            self.assertEqual(result["executions"], 1)

    def test_callback_observes_fresh_copy_for_each_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            paths = []
            def runner(workspace, timeout):
                self.assertFalse((workspace / "leftover").exists())
                (workspace / "leftover").write_text("x", encoding="utf-8", newline="\n")
                paths.append(str(workspace))
                return {"status": "passed" if len(paths) == 1 else "failed", "reason": "fixture"}
            result = run_mutation_checks(root, "subject.py", test_paths=["test_subject.py"], runner=runner, max_mutants=1)
            self.assertEqual(result["counts"]["killed"], 1)
            self.assertEqual(len(set(paths)), 2)
            self.assertTrue(all(not Path(path).exists() for path in paths))
            self.assertFalse((root / "leftover").exists())

    def test_callback_errors_invalid_results_and_nan_are_inconclusive(self):
        def bad_runner(workspace, timeout):
            raise RuntimeError("private path is not copied into error message")
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            for runner in (bad_runner, lambda *_: {"status": "guessed"}, lambda *_: {"status": "passed", "x": float("nan")}):
                with self.subTest(runner=runner):
                    result = run_mutation_checks(root, "subject.py", test_paths=["test_subject.py"], runner=runner)
                    self.assertEqual(result["status"], "baseline_inconclusive")
                    self.assertNotIn("private path", json.dumps(result))

    def test_attempt_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            calls = []
            def runner(*_):
                calls.append(1)
                return {"status": "passed"}
            result = run_mutation_checks(root, "subject.py", test_paths=["test_subject.py"], runner=runner, max_mutants=1)
            self.assertEqual(result["executions"], 2)
            self.assertEqual(len(calls), 2)

    def test_original_source_and_manifest_hashes_are_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            result = self.run_project(root)
            self.assertEqual(result["source_sha256"], hashlib.sha256(SOURCE.encode()).hexdigest())
            self.assertEqual([x["path"] for x in result["selected_manifest"]], ["subject.py", "test_subject.py"])
            self.assertIsNone(result["measurements"]["host_tokens"])
            self.assertFalse(result["boundaries"]["security_sandbox"])

    def test_path_escapes_and_absolute_paths_rejected_before_runner(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            for path in ("../subject.py", str(root / "subject.py"), "./subject.py", "C:/subject.py", "folder\\subject.py", "subject.py\x00"):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    run_mutation_checks(root, path, test_paths=["test_subject.py"], runner=lambda *_: self.fail("launched"))

    def test_selected_symlink_and_symlinked_parent_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            try:
                (root / "link.py").symlink_to(root / "subject.py")
                (root / "linked_dir").symlink_to(root, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation unavailable")
            for path in ("link.py", "linked_dir/subject.py"):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    run_mutation_checks(root, path, test_paths=["test_subject.py"], runner=lambda *_: self.fail("launched"))

    def test_source_byte_and_ast_limits(self):
        for source in ("a" * (128 * 1024 + 1), "x = 0\n" * 4000):
            with self.subTest(size=len(source)), self.assertRaises(ValueError):
                generate_mutants(source)

    def test_header_only_test_does_not_false_kill_source_formatting(self):
        header = "# SPDX-License-Identifier: MIT\n"
        source = header + "def positive(x):\n return x > 0\n"
        test = ("import unittest\nfrom pathlib import Path\nclass Header(unittest.TestCase):\n"
                " def test_header(self):\n  self.assertTrue(Path('subject.py').read_text(encoding='utf-8').startswith('# SPDX-License-Identifier: MIT'))\n")
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory, test, source)
            result = run_mutation_checks(root, "subject.py", test_paths=["test_subject.py"],
                                         command=[sys.executable, "-m", "unittest", "test_subject"])
            self.assertEqual(result["baseline"]["status"], "passed")
            self.assertEqual(result["counts"]["killed"], 0)
            self.assertEqual(result["counts"]["survived"], 2)
            self.assertTrue(all(m["source"].startswith(header) for m in generate_mutants(source)))

    def test_operator_edits_preserve_unicode_comments_and_chained_comparisons(self):
        source = ("# café and π\ndef f(élément, valeurs):\n"
                  "    return (élément) is not (None) and élément not in valeurs and 0 < élément <= 10\n")
        mutations = generate_mutants(source, max_mutants=10)
        self.assertTrue(any(x["description"] == "IsNot -> Is" for x in mutations))
        self.assertTrue(any(x["description"] == "NotIn -> In" for x in mutations))
        self.assertTrue(any(x["description"] == "Lt -> LtE" for x in mutations))
        self.assertTrue(any(x["description"] == "LtE -> Lt" for x in mutations))
        for mutation in mutations:
            self.assertTrue(mutation["source"].startswith("# café and π\n"))
            ast.parse(mutation["source"], feature_version=(3, 10))

    def test_fstring_mutation_preserves_expression_type(self):
        source = 'value = f"result:{1}"\n'
        for mutant in generate_mutants(source):
            self.assertTrue(mutant["source"].startswith('value = f"result:'))
            ast.parse(mutant["source"])

    def test_ignored_callback_deadline_is_inconclusive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            def runner(*_):
                time.sleep(0.02)
                return {"status": "passed"}
            result = run_mutation_checks(root, "subject.py", test_paths=["test_subject.py"], runner=runner,
                                         timeout_seconds=0.005, max_seconds=1)
            self.assertEqual(result["status"], "baseline_inconclusive")
            self.assertEqual(result["baseline"]["reason"], "attempt_time_budget_exhausted")

    def test_oversized_callback_result_is_inconclusive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            result = run_mutation_checks(root, "subject.py", test_paths=["test_subject.py"],
                                         runner=lambda *_: {"status": "passed", "log": "x" * 40000})
            self.assertEqual(result["baseline"]["reason"], "runner_result_size_limit")

    def test_malformed_failure_counts_are_not_called_killed(self):
        transcript = "Ran 1 test in 0.001s\nFAILED (failures=1, errors=" + "9" * 15 + ")\n"
        with tempfile.TemporaryDirectory() as directory:
            result = run_unittest_command([sys.executable, "-c", f"import sys;print({transcript!r});sys.exit(1)"], Path(directory), 1)
            self.assertEqual(result["status"], "incomplete")

    def test_directory_traversal_depth_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            deep = root / "support"
            for _ in range(18):
                deep = deep / "sub"
            deep.mkdir(parents=True)
            with self.assertRaises(ValueError):
                run_mutation_checks(root, "subject.py", test_paths=["test_subject.py"], support_paths=["support"],
                                     runner=lambda *_: self.fail("launched"))

    def test_validation_rejects_invalid_budgets_and_argv(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            for kwargs in ({"max_mutants": True}, {"max_seconds": float("inf")}, {"timeout_seconds": 0}, {"max_mutants": 129}):
                with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                    run_mutation_checks(root, "subject.py", test_paths=["test_subject.py"], runner=lambda *_: {"status": "passed"}, **kwargs)
            for command in ("python -m unittest", [], ["x\x00"]):
                with self.subTest(command=command), self.assertRaises(ValueError):
                    run_mutation_checks(root, "subject.py", test_paths=["test_subject.py"], command=command)
            with self.assertRaises(ValueError):
                run_mutation_checks(root, "subject.py", test_paths=["test_subject.py"], command=[sys.executable], runner=lambda *_: {})


if __name__ == "__main__":
    unittest.main()
