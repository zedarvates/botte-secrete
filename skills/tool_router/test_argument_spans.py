"""Fresh software-contract examples, not a model-quality evaluation corpus."""
import copy
import json
from pathlib import Path

import pytest

from . import argument_spans as candidate
from .memory_pilot import memory_call


def proposal(query, tool="memory_history", spans=None):
    return {"schema_version": candidate.CONTRACT_VERSION,
            "query_sha256": candidate.query_sha256(query), "tool_name": tool,
            "argument_spans": {} if spans is None else spans}


@pytest.mark.parametrize("tool,argument,text", [
    ("memory_context", "query", "roues en nylon"),
    ("memory_observations", "query", "journal d’essai"),
    ("memory_history", "key", "lot_MOTEUR-8"),
    ("memory_wiki", "query", "Arrosage saisonnier"),
    ("memory_scribe", "text", "  Ve\u0301rifier 🛠️ la vanne\t  "),
])
def test_exact_copy_preserves_case_whitespace_unicode_and_memory_contract(tool, argument, text):
    query = "🧰 Passage fourni : «" + text + "»."
    start = query.index(text)
    item = proposal(query, tool, {argument: {"start": start, "end": start + len(text)}})
    before = copy.deepcopy(item)
    route = candidate.bind_argument_spans(query, item)
    assert not route.abstained and not route.executable
    assert route.confidence == 0 and route.arguments == {argument: text}
    assert route.arguments[argument].encode("utf-8") == text.encode("utf-8")
    assert item == before
    call = memory_call(route, "host-project")
    assert call["arguments"]["project_id"] == "host-project"
    assert "actor_id" not in call["arguments"]


@pytest.mark.parametrize("tool", ["memory_context", "memory_observations", "memory_wiki"])
def test_optional_argument_omission_stays_omitted(tool):
    query = "Présente la vue complète disponible."
    route = candidate.bind_argument_spans(query, proposal(query, tool))
    assert not route.abstained and route.arguments == {}
    assert "query" not in memory_call(route, "host-project")["arguments"]


@pytest.mark.parametrize("span", [
    {"start": -1, "end": 2}, {"start": 0, "end": 99},
    {"start": 2, "end": 1}, {"start": 1, "end": 1},
    {"start": True, "end": 2}, {"start": 0, "end": False},
    {"start": 0.0, "end": 2}, {"start": "0", "end": 2},
    {"start": 0}, {"start": 0, "end": 2, "text": "rewrite"},
    [0, 2], "copied text",
])
def test_invalid_spans_abstain_without_partial_arguments(span):
    query = "lot_Z-4"
    route = candidate.bind_argument_spans(query, proposal(query, spans={"key": span}))
    assert route.abstained and route.arguments == {} and not route.executable
    assert route.reason == "invalid_argument_span"


@pytest.mark.parametrize("tool,spans", [
    ("memory_history", {}), ("memory_scribe", {}),
    ("memory_history", {"key": {"start": 0, "end": 9}}),
    ("memory_scribe", {"text": {"start": 0, "end": 257}}),
])
def test_final_memory_schema_remains_authoritative(tool, spans):
    query = "../secret" + "x" * 260
    route = candidate.bind_argument_spans(query, proposal(query, tool, spans))
    assert route.abstained and route.reason == "invalid_arguments"


@pytest.mark.parametrize("field", ["project_id", "actor_id", "trust_class", "executable"])
def test_model_cannot_supply_authority_arguments(field):
    query = "owner"
    route = candidate.bind_argument_spans(query, proposal(query, "memory_wiki", {
        field: {"start": 0, "end": len(query)},
    }))
    assert route.abstained and route.reason == "unexpected_argument"


def test_stale_digest_extra_fields_write_tools_and_invalid_envelopes_are_rejected():
    query = "lot_A-7"
    valid = proposal(query, spans={"key": {"start": 0, "end": len(query)}})
    changed = "lot_B-7"
    assert candidate.bind_argument_spans(changed, valid).reason == "query_digest_mismatch"
    for item in ([], {}, {**valid, "execute": True}, {**valid, "schema_version": "v0"},
                 {**valid, "tool_name": "memory_forget"}, {**valid, "tool_name": []},
                 {**valid, "argument_spans": []}):
        route = candidate.bind_argument_spans(query, item)
        assert route.abstained and not route.executable and route.arguments == {}


@pytest.mark.parametrize("query", [None, 42, "", " \t ", "x" * 513, "é" * 257, "\ud800"])
def test_invalid_queries_fail_closed(query):
    route = candidate.bind_argument_spans(query, {})
    assert route.abstained and route.reason == "invalid_query"


def test_explicit_abstention_requires_no_argument_spans():
    query = "Aucune consultation demandée."
    assert candidate.bind_argument_spans(query, proposal(query, None)).reason == "model_abstained"
    item = proposal(query, None, {"query": {"start": 0, "end": 6}})
    assert candidate.bind_argument_spans(query, item).reason == "abstention_with_arguments"


def test_valid_spans_are_not_semantic_or_negation_validation():
    query = "Ne consulte pas les anciennes notes sur roulement_X-2."
    start = query.index("anciennes")
    item = proposal(query, "memory_wiki", {"query": {"start": start, "end": start + 9}})
    route = candidate.bind_argument_spans(query, item)
    # A valid but unsuitable selection still copies literally; it cannot execute.
    assert route.arguments == {"query": "anciennes"}
    assert not route.abstained and not route.executable and route.confidence == 0


def test_example_cli_is_reproducible_and_does_not_overwrite(tmp_path, capsys):
    root = Path(__file__).resolve().parents[2]
    source = root / "docs/examples/memory-argument-spans-v1.json"
    output = tmp_path / "result.json"
    assert candidate.main(["--input", str(source), "--output", str(output)]) == 0
    saved = output.read_bytes()
    expected = (root / "docs/validation/memory-argument-spans-example-v1.json").read_bytes()
    assert json.loads(saved) == json.loads(expected)
    result = json.loads(saved)
    assert result["route"]["arguments"] == {"key": "lot_MOTEUR-8"}
    assert result["new_inference_attempts"] == 0 and not result["model_quality_measured"]
    assert all(result[k] == v for k, v in candidate.BOUNDARY.items())
    capsys.readouterr()
    assert candidate.main(["--input", str(source), "--output", str(output)]) == 2
    assert output.read_bytes() == saved
    assert json.loads(capsys.readouterr().out)["detail"] == "output exists"


@pytest.mark.parametrize("raw", [b'{"query":"one","query":"two"}', b'{}', b'x' * 8193])
def test_cli_rejects_invalid_json_shape_and_size_without_output(tmp_path, capsys, raw):
    source, output = tmp_path / "input.json", tmp_path / "output.json"
    source.write_bytes(raw)
    assert candidate.main(["--input", str(source), "--output", str(output)]) == 2
    assert not output.exists()
    assert json.loads(capsys.readouterr().out)["activation_allowed"] is False


def test_cli_reports_invalid_proposals_as_abstention_with_error_exit(tmp_path, capsys):
    source, output = tmp_path / "input.json", tmp_path / "output.json"
    source.write_text(json.dumps({"query": "lot_C-9", "proposal": {}}), encoding="utf-8")
    assert candidate.main(["--input", str(source), "--output", str(output)]) == 2
    result = json.loads(output.read_text(encoding="utf-8"))
    assert not result["valid_proposal"] and result["route"]["tool_name"] is None
