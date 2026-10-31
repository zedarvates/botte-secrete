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
    def test_readme_command_errors_retain_type_and_timeout_without_changing_verdict(self):
        spec = importlib.util.spec_from_file_location(
            'readme_smoke_under_test', Path(__file__).with_name('test_readme_commands.py'))
        smoke = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(smoke)
        command = 'python -m skills.checkup.cli .'
        errors = [
            (smoke.subprocess.TimeoutExpired(command, 30), 'TimeoutExpired, timeout=30s'),
            (FileNotFoundError('private diagnostic text'), 'FileNotFoundError'),
            (RuntimeError('private diagnostic text'), 'RuntimeError'),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            badge = f'version-{smoke.__version__}-'
            (root / 'README.md').write_text(badge + '\n```bash\n' + command + '\n```\n', encoding='utf-8')
            (root / 'README.fr.md').write_text(badge, encoding='utf-8')
            (root / 'pyproject.toml').write_text(f'version = "{smoke.__version__}"\n', encoding='utf-8')
            for error, expected in errors:
                with self.subTest(error=expected), patch.object(smoke, 'REPO', root), \
                     patch.object(smoke.subprocess, 'run', side_effect=error), \
                     contextlib.redirect_stdout(io.StringIO()) as output:
                    code = smoke.main()
                self.assertEqual(code, 1)
                self.assertIn(expected, output.getvalue())
                self.assertIn('1 passed, 1 failed', output.getvalue())
                self.assertNotIn('private diagnostic text', output.getvalue())

    def test_parcimonia_behavioral_contracts_are_selected_for_changed_inputs(self):
        for path in ["skills/preflight/assessment.py", "skills/preflight/github_plan.py",
                     "skills/preflight/github_evidence.py", "skills/llm_mcp/server.py",
                     "skills/skill_finder/finder.py", "scripts/run_tests.py"]:
            with self.subTest(path=path):
                labels = {runner.SUITES[index][0] for index in runner._suites_for_changes([path])}
                self.assertIn("parcimonia", labels)
        command = next(command for label, command, _ in runner.SUITES if label == "parcimonia")
        self.assertIn("skills.preflight.test_parcimonia", command)

    def test_distribution_suite_is_selected_for_every_contract_input(self):
        inputs = [
            'plugins/botte-secrete/.codex-plugin/plugin.json',
            'plugins/botte-secrete/assets/logo.svg',
            'plugins/botte-secrete/skills/botte-secrete/SKILL.md',
            '.agents/plugins/marketplace.json', 'pyproject.toml', 'skills/__init__.py',
            'skills/llm_mcp/server.py', 'skills/plugins/test_distribution.py',
            'skills/plugins/installer.py', 'LICENSE', 'scripts/run_tests.py',
            'scripts/test_runner_exit_verdict.py',
        ]
        for path in inputs:
            with self.subTest(path=path):
                labels = {runner.SUITES[index][0] for index in runner._suites_for_changes([path])}
                self.assertIn('codex_distribution', labels)
                self.assertIn('e2e', labels)

    def test_unrelated_changes_preserve_other_suite_selection(self):
        for path in ['plugins/unrelated/SKILL.md', '.agents/other.json', 'pyproject.toml.bak']:
            with self.subTest(path=path):
                labels = {runner.SUITES[index][0] for index in runner._suites_for_changes([path])}
                self.assertNotIn('codex_distribution', labels)
        labels = {runner.SUITES[index][0] for index in runner._suites_for_changes(['skills/auto_router/router.py'])}
        self.assertIn('auto_router', labels)
        self.assertIn('router_outcome', labels)
        self.assertNotIn('codex_distribution', labels)

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
