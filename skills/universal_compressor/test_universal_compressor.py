"""Tests for universal_compressor skill."""
import json
import sys
import unittest
from skills.universal_compressor.compressor import (
    compress, restore, flush_store, stats,
    _detect_type, _compress_text, _compress_json,
    _compress_log, _compress_tool_output, _compress_code,
)


class TestAutoDetect(unittest.TestCase):
    def test_detect_json(self):
        assert _detect_type('{"a": 1}') == "json"

    def test_detect_log(self):
        content = "2026-07-04T12:00:00 ERROR something\n2026-07-04T12:00:01 WARN retry"
        assert _detect_type(content) == "log"

    def test_detect_code(self):
        content = "import os\n\ndef foo():\n    return 42\n"
        assert _detect_type(content) == "code"

    def test_detect_text(self):
        assert _detect_type("hello world") == "text"

    def test_detect_tool_output(self):
        content = "FAILED: connection refused\nexit code 1"
        assert _detect_type(content) == "tool_output"


class TestTextCompression(unittest.TestCase):
    def test_dedup_lines(self):
        content = "error\n" * 20  # "error" repeated 20 times — worth compressing
        result = _compress_text(content)
        assert "identical lines" in result.data
        assert result.ratio < 1.0

    def test_no_dedup_short_lines(self):
        content = "hello\nhello\nhello\nhello\nworld"  # 4 short lines, not worth compressing
        result = _compress_text(content)
        assert "identical lines" not in result.data  # marker bigger than content
        assert "hello" in result.data  # still has the content

    def test_collapse_blanks(self):
        content = "a\n\n\n\nb"
        result = _compress_text(content)
        assert result.data.count("\n\n") <= 1


class TestJSONCompression(unittest.TestCase):
    def test_compact(self):
        content = '{\n  "a": 1,\n  "b": 2\n}'
        result = _compress_json(content)
        assert " " not in result.data.strip('{}"')  # no pretty-print spaces
        assert result.ratio < 1.0

    def test_preserve_array(self):
        items = [{"id": i, "value": f"item_{i}"} for i in range(20)]
        content = json.dumps(items)
        result = _compress_json(content)
        assert json.loads(result.data) == items

    def test_invalid_json_falls_back(self):
        result = _compress_json("not json at all")
        assert result.data == "not json at all"


class TestLogCompression(unittest.TestCase):
    def test_pattern_dedup(self):
        lines = []
        for i in range(100):
            lines.append("ERROR repeated identical failure")
        content = "\n".join(lines)
        result = _compress_log(content)
        assert "identical lines" in result.data
        assert result.ratio < 0.1  # massive compression

    def test_small_log_passthrough(self):
        content = "line1\nline2"
        result = _compress_log(content)
        assert result.ratio == 1.0


class TestToolOutputCompression(unittest.TestCase):
    def test_preserve_all_lines(self):
        lines = [f"line_{i}" for i in range(500)]  # 500 lines → ~4K chars → over 3000 limit
        content = "\n".join(lines)
        result = _compress_tool_output(content)
        assert result.data == content

    def test_short_output_passthrough(self):
        content = "short output\n"
        result = _compress_tool_output(content)
        assert result.ratio == 1.0


class TestCodeCompression(unittest.TestCase):
    def test_preserve_comments(self):
        content = "x = 1  # this is a comment\ny = 2"
        result = _compress_code(content)
        assert result.data == content

    def test_preserve_imports(self):
        content = "import os\nimport sys\nimport json\n\ndef foo():\n    pass"
        result = _compress_code(content)
        assert result.data == content


class TestMainAPI(unittest.TestCase):
    def test_compress_auto(self):
        result = compress('{"a":1,"b":2}')
        assert result.content_type == "json"
        assert result.ratio <= 1.0

    def test_compress_with_type(self):
        result = compress("error\n" * 20, content_type="text")
        assert "identical lines" in result.data

    def test_reversible(self):
        flush_store()
        result = compress("secret content", content_type="text", reversible=True)
        assert result.reversible_key
        restored = restore(result.reversible_key)
        assert restored == "secret content"

    def test_restore_nonexistent(self):
        assert restore("nonexistent") is None

    def test_stats(self):
        flush_store()
        compress("data", content_type="text", reversible=True)
        s = stats()
        assert s["stored_originals"] == 1
        assert s["total_original_bytes"] > 0

    def test_never_expands_the_input(self):
        """A prompt with embedded code must retain both prose and source.

        This benchmark fixture previously expanded during import collapsing.
        The conservative code strategy now leaves it unchanged.
        """
        content = (
            "You are an AI assistant helping with code review.\n"
            "Please analyze the following code for potential issues:\n\n"
            "```python\ndef unsafe_function(user_input):\n"
            '    import os\n    os.system(f"echo {user_input}")\n```\n\n'
            "Identify security vulnerabilities and suggest fixes.\n"
            "Consider: injection attacks, input validation, error handling.\n"
        )
        result = compress(content, content_type="auto")
        assert result.compressed_size <= result.original_size
        assert result.data == content
        assert result.content_type == "code"


class TestCLIIntegration(unittest.TestCase):
    def test_imports(self):
        import skills.universal_compressor
        import skills.universal_compressor.cli
        import skills.universal_compressor.mcp_server


class TestEvidenceIntegrity(unittest.TestCase):
    def setUp(self):
        flush_store()

    def tearDown(self):
        flush_store()

    def test_shared_prefix_originals_remain_independently_restorable(self):
        originals = ["é" * 256 + suffix for suffix in ("pending", "failure")]
        results = [compress(s, reversible=True) for s in originals]
        self.assertNotEqual(results[0].reversible_key, results[1].reversible_key)
        for original, result in zip(originals, results):
            self.assertEqual(restore(result.reversible_key), original)

    def test_duplicate_original_is_one_entry(self):
        first = compress("unchanged", reversible=True)
        second = compress("unchanged", reversible=True)
        self.assertEqual(first.reversible_key, second.reversible_key)
        self.assertEqual(stats()["stored_originals"], 1)

    def test_empty_original_roundtrip(self):
        result = compress("", reversible=True)
        self.assertEqual(restore(result.reversible_key), "")

    def test_json_preserves_late_errors_nested_keys_and_long_values(self):
        obj = {f"key_{i}": i for i in range(12)}
        obj["jobs"] = [{"status": "pass"}] * 7 + [{"error": "FATAL: " + "é" * 300}]
        obj["deep"] = {"a": {"b": {"c": {"d": {"not_authorized": True}}}}}
        result = compress(json.dumps(obj), "json")
        self.assertEqual(json.loads(result.data), obj)

    def test_json_retains_exact_number_and_string_lexemes(self):
        original = '{ "value": 1.234567890123456789, "x": "a  b", "x": "c" }'
        result = compress(original, "json")
        self.assertIn("1.234567890123456789", result.data)
        self.assertIn('"a  b"', result.data)
        self.assertEqual(result.data.count('"x"'), 2)

    def test_invalid_json_is_unchanged(self):
        original = '{\n\n "unfinished": [1, 2,\n'
        self.assertEqual(compress(original, "json").data, original)

    def test_code_strings_imports_and_directives_are_exact(self):
        original = ('import os\nurl = "https://example.invalid/a#fragment"\n'
                    'value = """line one\n# not a comment\nline three"""\n'
                    '# Do not activate this candidate.\nprint(url)\n')
        result = compress(original, "code")
        self.assertEqual(result.data, original)
        compile(result.data, "fixture", "exec")

    def test_two_identical_final_lines_are_not_silently_dropped(self):
        original = "start\nkeep me\nkeep me"
        self.assertEqual(compress(original, "text").data, original)

    def test_distinct_log_values_and_rare_error_survive_in_order(self):
        lines = [f"INFO job={i} value={i * 2}" for i in range(80)]
        error = "FATAL " + "detail " * 50 + "NOT_AUTHORIZED"
        lines.insert(65, error)
        self.assertEqual(compress("\n".join(lines), "log").data.splitlines(), lines)

    def test_tool_output_keeps_middle_and_long_tail_errors(self):
        lines = [f"row {i}: " + "x" * 120 for i in range(80)]
        lines[40] = "FAILED: do not deploy"
        lines[-1] = "FATAL " + "cause " * 100
        original = "\n".join(lines)
        self.assertEqual(compress(original, "tool_output").data, original)

    def test_utf8_sizes_are_bytes(self):
        original = '{ "message": "é漢🙂" }'
        result = compress(original, "json", reversible=True)
        self.assertEqual(result.original_size, len(original.encode("utf-8")))
        self.assertEqual(result.compressed_size, len(result.data.encode("utf-8")))
        self.assertEqual(stats()["total_original_bytes"], len(original.encode("utf-8")))

    def test_mcp_does_not_truncate_compressed_data_or_empty_restore(self):
        from skills.universal_compressor.mcp_server import handle_request
        original = json.dumps({"message": "x" * 650, "error": "FATAL: late failure"})
        request = {"id": 1, "method": "tools/call", "params": {
            "name": "compress", "arguments": {"content": original, "content_type": "json"}}}
        result = json.loads(handle_request(request)["result"]["content"][0]["text"])
        self.assertEqual(json.loads(result["data"]), json.loads(original))
        empty = compress("", reversible=True)
        request["params"] = {"name": "restore", "arguments": {"key": empty.reversible_key}}
        self.assertEqual(handle_request(request)["result"]["content"][0]["text"], "")

    def test_hermes_mcp_does_not_truncate_compressed_data(self):
        from skills.hermes_bridge.mcp_server import handle_request
        original = json.dumps({"message": "x" * 650, "error": "FATAL: late failure"})
        request = {"id": 1, "method": "tools/call", "params": {
            "name": "compress_content", "arguments": {"content": original, "content_type": "json"}}}
        result = json.loads(handle_request(request)["result"]["content"][0]["text"])
        self.assertEqual(json.loads(result["data"]), json.loads(original))


if __name__ == "__main__":
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    failed = len(result.failures) + len(result.errors)
    print(f"RESULT: {result.testsRun - failed} passed, {failed} failed")
    raise SystemExit(0 if result.wasSuccessful() else 1)
