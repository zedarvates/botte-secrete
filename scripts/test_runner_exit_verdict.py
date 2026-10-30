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
    def test_workbench_contract_changes_select_real_aggregate(self):
        for path in ('skills/app_test/reducer.py', 'skills/preflight/conformance.py',
                     'skills/app_test/workbench.py', 'skills/cli.py'):
            with self.subTest(path=path):
                selected = {runner.SUITES[i][0] for i in runner._suites_for_changes([path])}
                self.assertIn('verification_workbench', selected)

    def test_prioritized_run_keeps_all_checks_and_observes_real_child_outcomes(self):
        from skills.app_test.prioritization import command_fingerprint
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            history_path = root / '.botte-cache' / 'test-history.json'
            history_path.parent.mkdir()
            command = [sys.executable, '-c', 'print("1 passed, 0 failed")']
            fail_command = [sys.executable, '-c', 'print("0 passed, 1 failed"); raise SystemExit(1)']
            history_path.write_text(json.dumps({'schema':'parcimonia.test-history/v1','runs':[
                {'label':'failure','command_sha256':command_fingerprint(fail_command),
                 'duration_ms':10,'outcome':'failed'}]}), encoding='utf-8')
            with patch.object(runner, 'REPO', root), \
                 patch.object(runner, 'TEST_SUMMARY_PATH', root / 'summary.json'), \
                 patch.object(runner, 'SUITES', [('passing',command,''),('failure',fail_command,'')]), \
                 patch.object(sys, 'argv', ['run_tests.py','--prioritize']), \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(runner.main(), 1)
            lines = output.getvalue()
            self.assertLess(lines.index('[FAIL] failure'), lines.index('[OK ] passing'))
            history = json.loads(history_path.read_text(encoding='utf-8'))
            self.assertEqual([r['label'] for r in history['runs']], ['failure','failure','passing'])
            self.assertEqual(json.loads((root/'summary.json').read_text(encoding='utf-8'))['suite_count'],2)

    def test_shared_mcp_diagnostics_select_both_consumers(self):
        labels = {runner.SUITES[index][0] for index in
                  runner._suites_for_changes(['skills/checkup/mcp.py'])}
        self.assertTrue({'infra_advisor', 'checkup'}.issubset(labels))
        for path in ['skills/infra_advisor/advisor.py', 'skills/plugins/installer.py']:
            with self.subTest(path=path):
                labels = {runner.SUITES[index][0] for index in runner._suites_for_changes([path])}
                self.assertIn('checkup', labels)

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
