import json
from pathlib import Path

from skills.tool_router.base import LexicalToolRouter, ToolSpec, validate_route
from skills.tool_router.benchmark import BenchmarkResult, EvaluationCase, benchmark, needle_activation_allowed
from skills.tool_router.needle_adapter import NeedleToolRouter
from skills.tool_router.eval_dataset import build_seed_cases, write_seed_dataset


TOOLS = [
    ToolSpec("read_file", "Read a local text file", {"type": "object", "properties": {"path": {"type": "string"}}, "required": []}),
    ToolSpec("run_checkup", "Inspect project health", {"type": "object", "properties": {}, "additionalProperties": False}),
]


def test_lexical_router_selects_unique_tool_without_fabricating_arguments():
    result = LexicalToolRouter().route("please read the file", TOOLS)
    assert result.tool_name == "read_file"
    assert result.executable


def test_lexical_router_abstains_on_ambiguity():
    tools = [ToolSpec("read_file", "read file"), ToolSpec("read_log", "read log")]
    assert LexicalToolRouter().route("read", tools).reason == "ambiguous_lexical_match"


def test_validation_rejects_extra_and_wrong_typed_arguments():
    assert validate_route("run_checkup", {"unsafe": True}, TOOLS, source="test").abstained
    assert validate_route("read_file", {"path": 2}, TOOLS, source="test").abstained


def test_needle_unavailable_and_input_limits_abstain():
    router = NeedleToolRouter()
    assert router.route("read", TOOLS).reason == "needle_assets_not_configured"
    assert NeedleToolRouter(engine=object()).route("x", TOOLS * 6).reason == "too_many_tools"


def test_needle_response_is_validated_before_executable_route():
    class Engine:
        def route(self, query, payload):
            return json.dumps({"tool_name": "read_file", "arguments": {"path": "README.md"}, "confidence": .9})
    result = NeedleToolRouter(engine=Engine()).route("read README", TOOLS)
    assert result.executable and result.arguments == {"path": "README.md"}


def test_benchmark_gate_requires_all_safety_thresholds():
    cases = [EvaluationCase("checkup", TOOLS, "run_checkup", {})]
    result = benchmark(LexicalToolRouter(), cases)
    assert result.total == 1
    assert not result.meets_needle_gate(0.0)


def test_needle_activation_fails_closed_without_or_below_baseline():
    good = BenchmarkResult(20, .96, .99, 1.0, 0, 2.0, 100)
    slow_local = BenchmarkResult(20, .8, .8, .8, 0, 3.0, 100)
    assert not needle_activation_allowed(good, None)
    assert needle_activation_allowed(good, slow_local)
    assert not needle_activation_allowed(BenchmarkResult(20, .96, .99, 1.0, 1, 2.0, 100), slow_local)


def test_seed_dataset_is_bilingual_and_has_over_200_safe_cases(tmp_path):
    cases = build_seed_cases()
    assert len(cases) >= 200
    assert {case["language"] for case in cases} == {"fr", "en"}
    assert {case["kind"] for case in cases} == {"valid", "ambiguous", "abstain"}
    destination = tmp_path / "eval_dataset.jsonl"
    assert write_seed_dataset(destination) == len(cases)
    assert len(destination.read_text(encoding="utf-8").splitlines()) == len(cases)


def test_tracked_seed_dataset_is_jsonl_with_over_200_cases():
    dataset = Path(__file__).with_name("eval_dataset.jsonl")
    cases = [json.loads(line) for line in dataset.read_text(encoding="utf-8").splitlines()]
    assert len(cases) >= 200
    assert {case["language"] for case in cases} == {"fr", "en"}
    assert {case["kind"] for case in cases} == {"valid", "ambiguous", "abstain"}
