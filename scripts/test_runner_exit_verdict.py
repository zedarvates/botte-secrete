"""Exercise runner verdicts with real child exit codes and persisted summaries."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('runner_under_test', Path(__file__).with_name('run_tests.py'))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class ExitVerdictTests(unittest.TestCase):
    def check_case(self, text, child_exit, expected_failed):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summary = root / 'summary.json'
            command = [sys.executable, '-c', f'import sys; print({text!r}); sys.exit({child_exit})']
            with patch.object(runner, 'REPO', root), \
                 patch.object(runner, 'TEST_SUMMARY_PATH', summary), \
                 patch.object(runner, 'SUITES', [('fixture', command, '')]), \
                 patch.object(sys, 'argv', ['run_tests.py', '-q']), \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                code = runner.main()
            data = json.loads(summary.read_text(encoding='utf-8'))
            self.assertEqual(code, 1 if expected_failed else 0)
            self.assertEqual(data['failed'], expected_failed)
            self.assertEqual(data['status'], 'failed' if expected_failed else 'passed')
            self.assertEqual(data['suite_count'], 1)
            self.assertFalse(data['partial'])
            if expected_failed:
                self.assertNotIn('All 1 suites passed', output.getvalue())

    def test_nonzero_exit_overrides_passing_summary(self):
        self.check_case('1 passed, 0 failed', 2, 1)

    def test_successful_process_and_summary_pass(self):
        self.check_case('1 passed, 0 failed', 0, 0)

    def test_failed_summary_is_preserved(self):
        self.check_case('1 passed, 3 failed', 1, 3)

    def test_failed_summary_overrides_zero_exit(self):
        self.check_case('0 passed, 1 failed', 0, 1)

    def test_nonzero_without_summary_fails(self):
        self.check_case('child crashed', 2, 1)


if __name__ == '__main__':
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(ExitVerdictTests))
    failed = len(result.failures) + len(result.errors)
    print(f'{result.testsRun - failed} passed, {failed} failed')
    raise SystemExit(0 if result.wasSuccessful() else 1)
