"""Root scope, shared byte budget and partial-result contracts."""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from skills.fast_context import batch
from skills.cli import main


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'project'
        self.root.mkdir()
        self.gd = self.root / 'client.gd'
        self.zig = self.root / 'server.zig'
        self.gd.write_bytes(b'func spawn():\r\n    pass\r\n')
        self.zig.write_bytes(b'pub fn spawn() void {\n    return;\n}\n')
        self.request = {'schema': 'botte.code-context-request/v1', 'items': [
            {'id': 'client', 'file': 'client.gd', 'name': 'spawn'},
            {'id': 'server', 'file': 'server.zig', 'name': 'spawn'}]}

    def run_batch(self, request=None, **kwargs):
        return batch.prepare_code_batch(self.request if request is None else request, str(self.root), **kwargs)

    def test_zig_gd_batch_and_accounting(self):
        report = self.run_batch()
        self.assertEqual(report['status'], 'completed')
        self.assertEqual(report['items_completed'], 2)
        self.assertFalse(report['atomic_project_snapshot'])
        self.assertEqual(report['context_bytes'], len(self.gd.read_bytes()) + len(self.zig.read_bytes()))
        for row in report['items']:
            raw = (self.root / row['file']).read_bytes()
            self.assertEqual(row['bundle']['context']['text'].encode(), raw)
            self.assertEqual(row['bundle']['reference_sha256'], hashlib.sha256(raw).hexdigest())

    def test_stale_item_does_not_hide_good_item(self):
        self.request['items'][0]['expected_sha256'] = '0' * 64
        report = self.run_batch()
        self.assertEqual(report['status'], 'incomplete')
        self.assertEqual([r['status'] for r in report['items']], ['stale_source', 'completed'])
        self.assertEqual(report['items'][0]['bundle']['context']['text'], '')
        self.assertEqual(report['items_completed'], 1)

    def test_ambiguity_is_not_accepted(self):
        self.gd.write_text('func spawn():\nfunc spawn():\n', encoding='utf-8')
        report = self.run_batch()
        self.assertEqual(report['status'], 'incomplete')
        self.assertEqual(report['items'][0]['status'], 'ambiguous')
        self.request['items'][0]['occurrence'] = 2
        self.assertEqual(self.run_batch()['status'], 'completed')

    def test_missing_symbol_and_unreadable_file_remain_distinct(self):
        self.request['items'][0]['name'] = 'absent'
        self.zig.unlink()
        report = self.run_batch()
        self.assertEqual([r['status'] for r in report['items']], ['not_found', 'read_error'])
        self.assertEqual(report['items_completed'], 0)

    def test_shared_budget_skips_without_opening_later_source(self):
        self.gd.write_text('func spawn():\n' + '    pass\n' * 90, encoding='utf-8')
        self.request['items'][0].update(before=0, after=90)
        real = batch.prepare_code_context
        with patch.object(batch, 'prepare_code_context', wraps=real) as prepare:
            report = self.run_batch(max_context_bytes=256)
        self.assertLessEqual(report['context_bytes'], 256)
        self.assertEqual(prepare.call_count, 1)
        self.assertEqual(report['status'], 'incomplete')
        self.assertEqual(report['limited_windows'], 1)
        self.assertEqual(report['items'][1]['status'], 'budget_exhausted')

    def test_oversized_anchor_does_not_consume_other_items_budget(self):
        self.gd.write_text('func spawn(): #' + 'x' * 300, encoding='utf-8')
        report = self.run_batch(max_context_bytes=256)
        self.assertEqual([r['status'] for r in report['items']], ['context_over_budget', 'completed'])
        self.assertEqual(report['context_bytes'], len(self.zig.read_bytes()))

    def test_malformed_manifest_rejected_before_source_reads(self):
        bad_requests = [None, {}, {'schema': 'wrong', 'items': []},
                        {'schema': 'botte.code-context-request/v1', 'items': []}]
        for change in ({'file': '../outside.gd'}, {'file': '/outside.gd'}, {'file': 'C:/x.gd'},
                       {'file': 'src\\x.gd'}, {'file': 'x.py'}, {'file': 'x\x00.gd'},
                       {'expected_sha256': None}, {'occurrence': True}, {'before': -1},
                       {'after': 101}, {'name': '.*'}, {'unknown': 1}, {'id': 'client'}):
            request = copy.deepcopy(self.request)
            request['items'][1].update(change)
            bad_requests.append(request)
        request = copy.deepcopy(self.request)
        request['items'] = request['items'] * 9
        bad_requests.append(request)
        for request in bad_requests:
            with self.subTest(request=str(request)[:100]):
                with patch.object(batch, 'prepare_code_context') as prepare:
                    with self.assertRaises(ValueError):
                        batch.prepare_code_batch(request, str(self.root))
                    prepare.assert_not_called()

    def test_invalid_global_bounds(self):
        for value in (True, 0, 255, 131073, 1.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.run_batch(max_context_bytes=value)
        with self.assertRaises(ValueError):
            batch.prepare_code_batch(self.request, str(self.root / 'missing'))

    def test_parent_and_leaf_symlinks_refused(self):
        outside = Path(self.tmp.name) / 'outside'
        outside.mkdir()
        (outside / 'x.gd').write_text('func spawn():\n', encoding='utf-8')
        try:
            (self.root / 'link').symlink_to(outside, target_is_directory=True)
            (self.root / 'leaf.gd').symlink_to(self.gd)
        except (OSError, NotImplementedError):
            self.skipTest('symlink creation unavailable')
        for file in ('link/x.gd', 'leaf.gd'):
            request = copy.deepcopy(self.request)
            request['items'][0]['file'] = file
            with self.subTest(file=file), self.assertRaises(ValueError):
                self.run_batch(request)

    def test_changed_repeated_file_is_not_mixed_into_result(self):
        self.request['items'][1] = {'id': 'second', 'file': 'client.gd', 'name': 'spawn'}
        real = batch.prepare_code_context
        calls = []
        def prepare_then_change(*args, **kwargs):
            result = real(*args, **kwargs)
            calls.append(result)
            if len(calls) == 1:
                self.gd.write_text('func spawn():\n    new_revision_marker = 42\n', encoding='utf-8')
            return result
        with patch.object(batch, 'prepare_code_context', side_effect=prepare_then_change):
            report = self.run_batch()
        self.assertEqual(report['status'], 'incomplete')
        self.assertEqual(report['items'][1]['status'], 'source_changed_between_items')
        self.assertNotIn('bundle', report['items'][1])
        self.assertNotIn('new_revision_marker', json.dumps(report))
        self.assertEqual(report['context_bytes'], len(calls[0]['context']['text'].encode()))

    def test_request_reader_refuses_invalid_json(self):
        path = Path(self.tmp.name) / 'request.json'
        for raw in (b'{"schema":1,"schema":2}', b'{"items":NaN}', b'\xff', b'x' * 65537):
            path.write_bytes(raw)
            with self.subTest(raw=raw[:50]), self.assertRaises(ValueError):
                batch.read_batch_request(str(path))

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'FIFO unavailable')
    def test_request_fifo_refused_without_blocking(self):
        path = Path(self.tmp.name) / 'pipe.json'
        os.mkfifo(path)
        with self.assertRaises(ValueError):
            batch.read_batch_request(str(path))

    def test_console_and_actual_process(self):
        path = Path(self.tmp.name) / 'request.json'
        path.write_text(json.dumps(self.request), encoding='utf-8')
        args = ['code', 'batch', str(path), '--root', str(self.root)]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(args), 0)
        self.assertEqual(json.loads(out.getvalue())['items_completed'], 2)
        command = [sys.executable, '-m', 'skills.cli', *args]
        run = subprocess.run(command, capture_output=True, timeout=15)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.request['items'][0]['expected_sha256'] = '0' * 64
        path.write_text(json.dumps(self.request), encoding='utf-8')
        run = subprocess.run(command, capture_output=True, timeout=15)
        self.assertEqual(run.returncode, 6, run.stderr)
        self.assertEqual(json.loads(run.stdout)['status'], 'incomplete')
        path.write_text('{"invalid":true}', encoding='utf-8')
        run = subprocess.run(command, capture_output=True, timeout=15)
        self.assertEqual(run.returncode, 2)
        self.assertEqual(run.stdout, b'')


if __name__ == '__main__':
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(BatchTests))
    print(f'{result.testsRun - len(result.failures) - len(result.errors)} passed, {len(result.failures) + len(result.errors)} failed')
    raise SystemExit(0 if result.wasSuccessful() else 1)
