"""Tests for the append-only loop ledger."""

from skills.loop_optimizer.ledger import LoopLedger
from skills.loop_optimizer.models import LoopAction, LoopOutcome, ProgressState


def test_ledger_roundtrip_filter_and_summary(tmp_path):
    ledger = LoopLedger(tmp_path / "ledger.jsonl")
    ledger.append(LoopOutcome("a", 0, LoopAction.RETRY_LOCAL, ProgressState.PROGRESS,
                              context_tokens=10, execution_tokens=20))
    ledger.append(LoopOutcome("a", 1, LoopAction.VERIFY, ProgressState.SOLVED,
                              verification_tokens=5, success=True, cache_hit=True))
    ledger.append(LoopOutcome("b", 0, LoopAction.STOP, ProgressState.STALLED))
    with ledger.path.open("a", encoding="utf-8") as stream:
        stream.write("not-json\n")

    records = ledger.read("a")
    summary = ledger.summarize(records)

    assert len(records) == 2
    assert summary["tokens_total"] == 35
    assert summary["cache_hits"] == 1
    assert summary["success"] is True
