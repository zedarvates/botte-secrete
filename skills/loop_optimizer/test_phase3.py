"""Tests for bounded contexts and persistent delta verification."""

from skills.context_windows.windows import WindowManager
from skills.harness_delta.verifier import DeltaVerifier
from skills.loop_optimizer.context import LoopContextBuilder


def test_structured_deltas_are_ordered_and_context_is_bounded(tmp_path):
    manager = WindowManager(store_path=tmp_path / "windows.json")
    manager.create_window("active", "one\ntwo", "active")
    manager.create_window("active", "one\nthree", "active")
    manager.create_window("reference", "reference content", "reference")
    builder = LoopContextBuilder(manager, max_context_tokens=15)

    delta = manager.structured_deltas()
    context = builder.build(references=("reference",), unresolved_errors=("test failed",))

    assert delta and delta[0].changed_lines == 1
    assert context.tokens <= 15
    assert context.included[0] == "active:active"
    assert context.dropped
    assert context.final_verification_required is True


def test_verifier_persists_and_final_verification_checks_everything(tmp_path):
    path = tmp_path / "verifier.json"
    verifier = DeltaVerifier(path)
    verifier.snapshot("safe", "unchanged")
    verifier.set_risk("risk", 0.8)
    restored = DeltaVerifier(path)
    sections = {"safe": "unchanged", "risk": "unchanged", "new": "value"}

    intermediate = restored.sections_to_verify(sections)
    final = restored.sections_to_verify(sections, final=True)

    assert {item["section"] for item in intermediate} == {"risk", "new"}
    assert {item["section"] for item in final} == set(sections)
