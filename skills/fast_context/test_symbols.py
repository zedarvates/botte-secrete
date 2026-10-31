"""Behavioral tests for lexical Zig/GDScript locations and actual CLI reads."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

from skills.fast_context.symbols import locate_symbol, locate_symbol_file, MAX_SOURCE_BYTES
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
            source.write_text('func spawn():\n', encoding='utf-8')
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
            path.write_text('pub fn spawn() void {}\n', encoding='utf-8')
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


if __name__ == '__main__':
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(SymbolTests))
    print(f'{result.testsRun - len(result.failures) - len(result.errors)} passed, {len(result.failures) + len(result.errors)} failed')
    raise SystemExit(0 if result.wasSuccessful() else 1)
