"""Tests for decision_ladder skill."""
import json
import tempfile
from pathlib import Path

from skills.decision_ladder.ladder import climb, audit_task_list, LadderResult, LADDER
from skills.decision_ladder.hook import pre_code_check, should_write_code, format_warning
from skills.decision_ladder.metrics import LadderMetrics


class TestClimb:
    def test_stdlib_detection(self):
        result = climb("parse JSON config file")
        assert result.rung == "stdlib"
        assert "json" in result.solution.lower()
        assert result.saved_lines > 0
        assert result.confidence > 0.5

    def test_regex_oneliner(self):
        result = climb("strip HTML tags from string")
        assert result.rung == "regex_oneliner"
        assert "re.sub" in result.solution or "replace" in result.solution.lower()

    def test_existing_module(self):
        result = climb("audit code quality and find dead code")
        assert result.rung == "existing_module"
        assert "fallow_like" in result.solution

    def test_new_code(self):
        result = climb("design a custom auth middleware with rate limiting")
        assert result.rung == "new_code"

    def test_edge_case_empty(self):
        result = climb("")
        assert result.rung == "new_code"

    def test_edge_case_gibberish(self):
        result = climb("xyzzy foobar quux")
        assert result.rung == "new_code"
        assert result.confidence > 0.5


class TestAudit:
    def test_mixed_tasks(self):
        tasks = [
            "parse JSON config",
            "design auth middleware",
            "count word frequency",
            "strip HTML tags",
            "implement custom solver",
        ]
        report = audit_task_list(tasks)
        assert report["total_tasks"] == 5
        assert report["lines_saved"] > 0
        assert "stdlib" in report["by_rung"] or "regex_oneliner" in report["by_rung"]

    def test_all_new_code(self):
        tasks = [
            "design a novel distributed consensus algorithm",
            "implement a custom blockchain VM",
        ]
        report = audit_task_list(tasks)
        assert report["new_code_needed"] == 2
        assert report["avoidable"] == 0

    def test_all_avoidable(self):
        tasks = [
            "parse JSON file",
            "strip HTML tags",
        ]
        report = audit_task_list(tasks)
        assert report["new_code_needed"] == 0
        assert report["avoidable_pct"] == 100


class TestHook:
    def test_pre_code_check_warning(self):
        result = pre_code_check("parse JSON file", strict=False)
        assert result.rung == "stdlib"

    def test_pre_code_check_new_code(self):
        result = pre_code_check("design a novel consensus algorithm", strict=False)
        assert result.rung == "new_code"

    def test_strict_mode_raises(self):
        try:
            pre_code_check("parse JSON file", strict=True)
            assert False, "Should have raised"
        except ValueError as e:
            assert "stdlib" in str(e)

    def test_should_write_code(self):
        assert not should_write_code("parse JSON file")
        assert should_write_code("implement novel algorithm")

    def test_format_warning_new_code(self):
        result = climb("design middleware")
        msg = format_warning(result)
        assert "✅" in msg or "new code is justified" in msg

    def test_format_warning_avoidable(self):
        result = climb("parse JSON file")
        msg = format_warning(result)
        assert "⚠️" in msg


class TestMetrics:
    def test_record_and_summary(self):
        m = LadderMetrics()
        m.record(task="parse JSON", rung="stdlib", saved=15, confidence=0.85)
        m.record(task="strip HTML", rung="regex_oneliner", saved=10, confidence=0.80)
        m.record(task="design auth", rung="new_code", saved=0, confidence=0.90)

        assert m.total_checks == 3
        assert m.tasks_avoided == 2
        assert m.avoidable_pct == 66.7
        assert m.total_lines_saved == 25
        assert m.avg_lines_saved == 12.5
        assert m.by_rung == {"stdlib": 1, "regex_oneliner": 1, "new_code": 1}

    def test_save_load_roundtrip(self):
        m = LadderMetrics()
        m.record(task="test", rung="stdlib", saved=5)
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = Path(f.name)
        try:
            m.save(path)
            loaded = LadderMetrics.load(path)
            assert loaded.total_checks == 1
            assert loaded.total_lines_saved == 5
        finally:
            path.unlink(missing_ok=True)

    def test_empty_metrics(self):
        m = LadderMetrics()
        assert m.avoidable_pct == 0.0
        assert m.avg_lines_saved == 0.0


class TestLadderStructure:
    def test_four_rungs(self):
        assert len(LADDER) == 4

    def test_rung_order(self):
        names = [r.name for r in LADDER]
        assert names == ["stdlib", "regex_oneliner", "existing_module", "new_code"]

    def test_rungs_have_descriptions(self):
        for r in LADDER:
            assert r.description
            assert r.check
            assert r.example
