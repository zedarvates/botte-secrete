"""Contracts for fresh versus caller-bound local source workflows."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from skills.fast_context import workflow
from skills.cli import main


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'client.gd'
        self.raw = b'# fixture\r\nfunc spawn():\r\n    pass\r\n'
        self.path.write_bytes(self.raw)
        self.digest = hashlib.sha256(self.raw).hexdigest()

    def test_fresh_observation_is_labeled(self):
        result = workflow.prepare_code_context(str(self.path), 'spawn')
        self.assertEqual(result['schema'], 'botte.code-context-bundle/v1')
        self.assertEqual(result['reference_origin'], 'fresh_discovery')
        self.assertEqual(result['reference_sha256'], self.digest)
        self.assertEqual(result['context']['text'].encode('utf-8'), self.raw)

    def test_explicit_reference_does_not_rediscover(self):
        with patch.object(workflow, 'locate_symbol_file', side_effect=AssertionError('rediscovery forbidden')):
            result = workflow.prepare_code_context(str(self.path), 'spawn', expected_sha256=self.digest)
        self.assertEqual(result['reference_origin'], 'caller_expected')
        self.assertEqual(result['status'], 'completed')

    def test_stale_explicit_reference_is_not_refreshed(self):
        self.path.write_bytes(self.raw + b'# changed\n')
        result = workflow.prepare_code_context(str(self.path), 'spawn', expected_sha256=self.digest)
        self.assertEqual(result['status'], 'stale_source')
        self.assertEqual(result['reference_sha256'], self.digest)
        self.assertEqual(result['context']['text'], '')

    def test_change_between_fresh_stages_is_not_retried(self):
        real = workflow.locate_symbol_file
        def discover_then_change(*args, **kwargs):
            result = real(*args, **kwargs)
            self.path.write_bytes(self.raw + b'# raced\n')
            return result
        with patch.object(workflow, 'locate_symbol_file', side_effect=discover_then_change) as discover:
            result = workflow.prepare_code_context(str(self.path), 'spawn')
        self.assertEqual(discover.call_count, 1)
        self.assertEqual(result['status'], 'stale_source')
        self.assertEqual(result['context']['text'], '')

    def test_duplicates_require_caller_selection(self):
        self.path.write_text('func spawn():\n    pass\nfunc spawn():\n    return\n', encoding='utf-8')
        self.assertEqual(workflow.prepare_code_context(str(self.path), 'spawn')['status'], 'ambiguous')
        selected = workflow.prepare_code_context(str(self.path), 'spawn', occurrence=2, before=0, after=1)
        self.assertEqual(selected['context']['text'], 'func spawn():\n    return\n')

    def test_missing_symbol_and_limits_stay_visible(self):
        missing = workflow.prepare_code_context(str(self.path), 'missing')
        self.assertEqual(missing['status'], 'not_found')
        self.assertEqual(missing['context']['text'], '')
        self.path.write_text('func spawn():\n' + '    pass\n' * 90, encoding='utf-8')
        limited = workflow.prepare_code_context(str(self.path), 'spawn', before=0, after=90, max_context_bytes=256)
        self.assertFalse(limited['context']['window_complete'])
        self.assertLessEqual(limited['context']['context_bytes'], 256)

    def test_invalid_parameters_propagate(self):
        for kwargs in ({'expected_sha256': ''}, {'expected_sha256': []}, {'before': -1},
                       {'occurrence': True}, {'max_context_bytes': 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                workflow.prepare_code_context(str(self.path), 'spawn', **kwargs)

    def test_console_dispatch(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(['code', 'bundle', str(self.path), 'spawn', '--expected-sha256', self.digest])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())['reference_origin'], 'caller_expected')
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(['code', 'symbol', str(self.path), 'spawn'])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())['source_sha256'], self.digest)

    def test_actual_process_and_stale_exit(self):
        command = [sys.executable, '-m', 'skills.cli', 'code', 'bundle', str(self.path), 'spawn']
        first = subprocess.run(command, capture_output=True, timeout=15)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(json.loads(first.stdout)['context']['text'].encode(), self.raw)
        self.path.write_bytes(self.raw + b'# changed\n')
        second = subprocess.run(command + ['--expected-sha256', self.digest], capture_output=True, timeout=15)
        self.assertEqual(second.returncode, 3, second.stderr)
        self.assertEqual(json.loads(second.stdout)['context']['text'], '')


if __name__ == '__main__':
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(WorkflowTests))
    print(f'{result.testsRun - len(result.failures) - len(result.errors)} passed, {len(result.failures) + len(result.errors)} failed')
    raise SystemExit(0 if result.wasSuccessful() else 1)
