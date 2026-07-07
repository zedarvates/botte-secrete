"""Tests for universal_compressor skill."""
import json
from skills.universal_compressor.compressor import (
    compress, restore, flush_store, stats,
    _detect_type, _compress_text, _compress_json,
    _compress_log, _compress_tool_output, _compress_code,
)


class TestAutoDetect:
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


class TestTextCompression:
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


class TestJSONCompression:
    def test_compact(self):
        content = '{\n  "a": 1,\n  "b": 2\n}'
        result = _compress_json(content)
        assert " " not in result.data.strip('{}"')  # no pretty-print spaces
        assert result.ratio < 1.0

    def test_truncate_array(self):
        items = [{"id": i, "value": f"item_{i}"} for i in range(20)]
        content = json.dumps(items)
        result = _compress_json(content)
        assert "more items" in result.data

    def test_invalid_json_falls_back(self):
        result = _compress_json("not json at all")
        assert result.content_type == "text"


class TestLogCompression:
    def test_pattern_dedup(self):
        lines = []
        for i in range(100):
            lines.append(f"2026-07-04T12:00:{i:02d} ERROR something failed retry={i}")
        content = "\n".join(lines)
        result = _compress_log(content)
        assert "unique patterns" in result.data
        assert result.ratio < 0.1  # massive compression

    def test_small_log_passthrough(self):
        content = "line1\nline2"
        result = _compress_log(content)
        assert result.ratio == 1.0


class TestToolOutputCompression:
    def test_head_tail(self):
        lines = [f"line_{i}" for i in range(500)]  # 500 lines → ~4K chars → over 3000 limit
        content = "\n".join(lines)
        result = _compress_tool_output(content)
        assert "omitted" in result.data.lower() or len(result.data) < len(content)

    def test_short_output_passthrough(self):
        content = "short output\n"
        result = _compress_tool_output(content)
        assert result.ratio == 1.0


class TestCodeCompression:
    def test_strip_comments(self):
        content = "x = 1  # this is a comment\ny = 2"
        result = _compress_code(content)
        assert "#" not in result.data

    def test_collapse_imports(self):
        content = "import os\nimport sys\nimport json\n\ndef foo():\n    pass"
        result = _compress_code(content)
        assert "import lines" in result.data
        assert result.ratio < 1.0


class TestMainAPI:
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
        """A natural-language prompt containing one short fenced code block is
        misdetected as 'code' (_detect_type counts def/import/braces, not
        prose ratio); strip_comments+collapse_imports on a single import line
        nets it larger (# [1 import lines] > 'import os'). compress() must
        never hand back something bigger than what came in — that would grow
        the context it's meant to shrink. Regression for the exact input that
        triggered it in scripts/benchmark_full.py's SAMPLE_PROMPT."""
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
        assert result.strategy == "none (would have expanded)"


class TestCLIIntegration:
    def test_imports(self):
        import skills.universal_compressor
        import skills.universal_compressor.cli
        import skills.universal_compressor.mcp_server
