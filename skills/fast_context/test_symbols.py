"""Behavioral tests for lexical Zig/GDScript locations and actual CLI reads."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

from skills.fast_context.symbols import locate_symbol, locate_symbol_file, read_symbol_context_file, MAX_SOURCE_BYTES
from skills.fast_context.cli import main


class SymbolTests(unittest.TestCase):
    def test_zig_exact_and_modifiers(self):
        source = 'fn other() void {}\npub inline fn spawn() void {}\nextern "c" fn spawn() void;\n'
        report = locate_symbol(source, 'zig', 'spawn')
        self.assertEqual([r['line'] for r in report['results']], [2, 3])
        self.assertEqual(report['results'][0]['snippet'], 'pub inline fn spawn() void {}')
        self.assertEqual(report['source_sha256'], hashlib.sha256(source.encode()).hexdigest())
        self.assertFalse(report['syntax_checked'])
        self.assertFalse(report['body_included'])

    def test_gdscript_static_and_nested(self):
        source = 'static func spawn(x: int) -> void:\n    pass\nclass Nested:\n\tfunc spawn():\n\t\tpass\n'
        report = locate_symbol(source, 'gdscript', 'spawn')
        self.assertEqual([r['line'] for r in report['results']], [1, 4])

    def test_zig_comments_strings_multiline(self):
        source = '// fn spawn() void {}\nconst a = "fn spawn()";\n  \\\\fn spawn() void {}\nfn spawn() void {}\n'
        self.assertEqual([r['line'] for r in locate_symbol(source, 'zig', 'spawn')['results']], [4])

    def test_gdscript_multiline_strings_and_comments(self):
        source = '# func spawn():\nvar a = """\nfunc spawn():\n"""\nvar b = \'\'\'\nfunc spawn():\n\'\'\'\nfunc spawn():\n    pass\n'
        self.assertEqual([r['line'] for r in locate_symbol(source, 'gdscript', 'spawn')['results']], [8])

    def test_escaped_quotes_do_not_create_declarations(self):
        source = 'var text = "escaped \\\" string"\nfunc spawn(): # comment\n    pass\n'
        self.assertEqual(locate_symbol(source, 'gdscript', 'spawn')['results'][0]['line'], 2)

    def test_prefix_and_case_are_not_exact(self):
        source = 'func spawn_more():\n    pass\nfunc Spawn():\n    pass\n'
        self.assertEqual(locate_symbol(source, 'gdscript', 'spawn')['total_candidates'], 0)

    def test_crlf_bom_and_unicode_line_separator(self):
        source = '\ufeff# note café\u2028other\r\nfunc spawn():\r\n    pass\r\n'
        report = locate_symbol(source, 'gdscript', 'spawn')
        self.assertEqual(report['results'][0]['line'], 2)
        self.assertEqual(report['source_bytes'], len(source.encode('utf-8')))

    def test_bom_first_declaration(self):
        self.assertEqual(locate_symbol('\ufeffpub fn spawn() void {}', 'zig', 'spawn')['total_candidates'], 1)

    def test_result_omissions(self):
        report = locate_symbol('func spawn():\n' * 5, 'gdscript', 'spawn', 2)
        self.assertEqual(len(report['results']), 2)
        self.assertEqual(report['omitted_candidates'], 3)
        self.assertEqual(report['total_candidates'], 5)

    def test_unicode_snippet_truncation(self):
        report = locate_symbol('func spawn(): #' + 'é' * 1000, 'gdscript', 'spawn')
        self.assertTrue(report['results'][0]['snippet_truncated'])
        self.assertLessEqual(len(report['results'][0]['snippet'].encode('utf-8')), 1024)

    def test_invalid_inputs(self):
        cases = [(None, 'zig', 'x', 1), ('x' * (MAX_SOURCE_BYTES + 1), 'zig', 'x', 1),
                 ('\x00', 'zig', 'x', 1), ('', 'python', 'x', 1), ('', [], 'x', 1),
                 ('', 'zig', 'x.*', 1), ('', 'zig', 'x' * 129, 1), ('', 'zig', 'x', True),
                 ('', 'zig', 'x', 0), ('', 'zig', 'x', 21)]
        for args in cases:
            with self.subTest(args=str(args)[:80]), self.assertRaises(ValueError):
                locate_symbol(*args)

    def test_actual_file_digest_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'client.gd'
            path.write_bytes(b'func spawn():\r\n    pass\r\n')
            first = locate_symbol_file(str(path), 'spawn')
            self.assertEqual(first['source_sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
            path.write_bytes(b'# changed\nfunc spawn():\n    pass\n')
            second = locate_symbol_file(str(path), 'spawn')
            self.assertNotEqual(first['source_sha256'], second['source_sha256'])
            self.assertEqual(second['results'][0]['line'], 2)

    def test_invalid_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'source.gd'
            for data in (b'\xff', b'\x00', b'x' * (MAX_SOURCE_BYTES + 1)):
                path.write_bytes(data)
                with self.assertRaises(ValueError):
                    locate_symbol_file(str(path), 'spawn')
            with self.assertRaises(ValueError):
                locate_symbol_file(str(Path(tmp) / 'source.py'), 'spawn')
            with self.assertRaises(OSError):
                locate_symbol_file(str(Path(tmp) / 'missing.gd'), 'spawn')
            path.unlink()
            path.mkdir()
            with self.assertRaises((OSError, ValueError)):
                locate_symbol_file(str(path), 'spawn')

    def test_leaf_symlink_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, link = Path(tmp) / 'real.gd', Path(tmp) / 'link.gd'
            source.write_text('func spawn():\n', encoding='utf-8', newline="\n")
            try:
                link.symlink_to(source)
            except (OSError, NotImplementedError):
                self.skipTest('symlink creation unsupported on this host')
            with self.assertRaises(ValueError):
                locate_symbol_file(str(link), 'spawn')

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'FIFO unavailable')
    def test_fifo_rejected_without_blocking(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'pipe.gd'
            os.mkfifo(path)
            with self.assertRaises(ValueError):
                locate_symbol_file(str(path), 'spawn')

    def test_real_cli_success_empty_and_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'server.zig'
            path.write_text('pub fn spawn() void {}\n', encoding='utf-8', newline="\n")
            for name, expected in (('spawn', 1), ('missing', 0)):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    status = main(['symbol', str(path), name])
                self.assertEqual(status, 0)
                self.assertEqual(json.loads(out.getvalue())['total_candidates'], expected)
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                status = main(['symbol', str(path), 'bad.*'])
            self.assertEqual(status, 2)
            self.assertEqual(out.getvalue(), '')
            self.assertIn('error', json.loads(err.getvalue()))


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'client.gd'
        self.source = '# before\r\nfunc spawn():\r\n    print("café")\r\n# after\r\n'
        self.path.write_bytes(self.source.encode('utf-8'))
        self.digest = hashlib.sha256(self.path.read_bytes()).hexdigest()

    def read(self, **kwargs):
        return read_symbol_context_file(str(self.path), 'spawn', self.digest, **kwargs)

    def test_exact_crlf_window_and_digest(self):
        report = self.read(before=1, after=1)
        expected = ''.join(self.source.splitlines(keepends=True)[:3])
        self.assertEqual(report['text'], expected)
        self.assertEqual((report['start_line'], report['end_line']), (1, 3))
        self.assertEqual(report['context_bytes'], len(expected.encode('utf-8')))
        self.assertEqual(report['context_sha256'], hashlib.sha256(expected.encode('utf-8')).hexdigest())
        self.assertTrue(report['window_complete'])
        self.assertIsNone(report['function_body_complete'])

    def test_stale_file_returns_no_source_text(self):
        self.path.write_text('func spawn():\n    secret_current_value = 42\n', encoding='utf-8', newline="\n")
        report = self.read()
        self.assertEqual(report['status'], 'stale_source')
        self.assertEqual(report['text'], '')
        self.assertNotIn('secret_current_value', json.dumps(report))
        self.assertNotEqual(report['source_sha256'], self.digest)

    def test_only_line_endings_changed_is_stale(self):
        self.path.write_bytes(self.source.replace('\r\n', '\n').encode('utf-8'))
        self.assertEqual(self.read()['status'], 'stale_source')

    def test_ambiguity_requires_explicit_occurrence(self):
        source = 'func spawn():\n    pass\nclass Nested:\n    func spawn():\n        pass\n'
        self.path.write_text(source, encoding='utf-8', newline="\n")
        self.digest = hashlib.sha256(source.encode()).hexdigest()
        report = self.read()
        self.assertEqual(report['status'], 'ambiguous')
        self.assertEqual(report['candidate_lines'], [1, 4])
        self.assertEqual(report['text'], '')
        self.assertEqual(self.read(occurrence=2, before=0, after=0)['text'], '    func spawn():\n')
        self.assertEqual(self.read(occurrence=3)['status'], 'not_found')

    def test_missing_symbol(self):
        report = read_symbol_context_file(str(self.path), 'missing', self.digest)
        self.assertEqual(report['status'], 'not_found')
        self.assertEqual(report['text'], '')

    def test_budget_retains_anchor_and_whole_lines(self):
        source = '# before' + 'x' * 300 + '\nfunc spawn():\n' + '    print("é")\n' * 50
        self.path.write_text(source, encoding='utf-8', newline="\n")
        self.digest = hashlib.sha256(source.encode()).hexdigest()
        report = self.read(before=1, after=50, max_context_bytes=256)
        self.assertEqual(report['start_line'], 2)
        self.assertLessEqual(report['context_bytes'], 256)
        self.assertTrue(report['text'].startswith('func spawn():\n'))
        self.assertTrue(report['text'].endswith('\n'))
        self.assertEqual(report['omitted_before_lines'], 1)
        self.assertGreater(report['omitted_after_lines'], 0)
        self.assertFalse(report['window_complete'])

    def test_anchor_exceeding_budget_returns_no_partial_declaration(self):
        source = 'func spawn(): #' + 'x' * 300
        self.path.write_text(source, encoding='utf-8', newline="\n")
        self.digest = hashlib.sha256(source.encode()).hexdigest()
        report = self.read(max_context_bytes=256)
        self.assertEqual(report['status'], 'context_over_budget')
        self.assertEqual(report['text'], '')

    def test_no_final_newline_and_bom(self):
        source = '\ufefffunc spawn():\n    pass'
        self.path.write_text(source, encoding='utf-8', newline="\n")
        self.digest = hashlib.sha256(source.encode()).hexdigest()
        self.assertEqual(self.read(before=20, after=100)['text'], source)

    def test_zig_context(self):
        path = self.path.with_suffix('.zig')
        source = 'pub fn spawn() void {\n    return;\n}\n'
        path.write_text(source, encoding='utf-8', newline="\n")
        result = read_symbol_context_file(str(path), 'spawn', hashlib.sha256(source.encode()).hexdigest())
        self.assertEqual(result['text'], source)
        self.assertEqual(result['language'], 'zig')

    def test_one_snapshot_binds_hash_and_content(self):
        from unittest.mock import patch
        from skills.fast_context import symbols
        original = symbols._read_source_file
        def read_then_change(path):
            snapshot = original(path)
            self.path.write_text('func changed():\n    pass\n', encoding='utf-8', newline="\n")
            return snapshot
        with patch.object(symbols, '_read_source_file', side_effect=read_then_change) as reader:
            report = self.read()
        self.assertEqual(reader.call_count, 1)
        self.assertEqual(report['source_sha256'], self.digest)
        self.assertEqual(report['text'], self.source)

    def test_invalid_context_arguments(self):
        for kwargs in ({'before': True}, {'before': -1}, {'before': 21}, {'after': 101},
                       {'after': 2.5}, {'max_context_bytes': 255}, {'max_context_bytes': 65537},
                       {'occurrence': True}, {'occurrence': 0}, {'occurrence': 21}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.read(**kwargs)
        for digest in ('bad', 'A' * 64, None, []):
            with self.subTest(digest=digest), self.assertRaises(ValueError):
                read_symbol_context_file(str(self.path), 'spawn', digest)

    def test_cli_ambiguous_and_over_budget_exits(self):
        for source, args, expected in (
                ('func spawn():\nfunc spawn():\n', [], 4),
                ('func spawn(): #' + 'x' * 300, ['--max-context-bytes', '256'], 5)):
            self.path.write_text(source, encoding='utf-8', newline="\n")
            digest = hashlib.sha256(source.encode()).hexdigest()
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = main(['context', str(self.path), 'spawn', digest, *args])
            self.assertEqual(code, expected)
            self.assertEqual(json.loads(out.getvalue())['text'], '')

    def test_actual_cli_statuses(self):
        def command(expected):
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = main(['context', str(self.path), 'spawn', expected])
            return code, out.getvalue(), err.getvalue()
        code, output, error = command(self.digest)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)['status'], 'completed')
        self.assertEqual(error, '')
        code, output, _ = command('0' * 64)
        self.assertEqual(code, 3)
        self.assertEqual(json.loads(output)['text'], '')
        code, output, error = command('bad')
        self.assertEqual(code, 2)
        self.assertEqual(output, '')
        self.assertIn('error', json.loads(error))


if __name__ == '__main__':
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromNames([__name__ + ".SymbolTests", __name__ + ".ContextTests"]))
    print(f'{result.testsRun - len(result.failures) - len(result.errors)} passed, {len(result.failures) + len(result.errors)} failed')
    raise SystemExit(0 if result.wasSuccessful() else 1)
