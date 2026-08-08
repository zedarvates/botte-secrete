"""Tests for deterministic automatic micro-NN grounding labels."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from skills.botte_nn import active_learning
from skills.botte_nn import auto_labels
from skills.response_cache import ResponseCache
from skills.universal_compressor.compressor import compress, flush_store


def _ok(message: str, condition: bool, state: list[int]) -> None:
    print(f"  [{'PASS' if condition else 'FAIL'}] {message}")
    state[0 if condition else 1] += 1


def _rows() -> list[dict]:
    path = active_learning.DATA_DIR / "inference_logs.jsonl"
    if not path.exists():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> int:
    state = [0, 0]
    print("== automatic grounding labels tests ==")
    original_data_dir = active_learning.DATA_DIR
    active_learning.DATA_DIR = Path(tempfile.mkdtemp()) / "active-learning"
    auto_labels._SEEN_BY_LOG.clear()
    flush_store()
    try:
        _ok("compression ratios map to stable none/delta/heavy labels",
            auto_labels.compression_label(1.0) == "none"
            and auto_labels.compression_label(0.7) == "delta"
            and auto_labels.compression_label(0.2) == "heavy", state)

        content = "ERROR repeated failure\n" * 100
        result = compress(
            content, content_type="text", reversible=True, learn=True
        )
        rows = _rows()
        _ok("exact reversible compression appends one verified oracle label",
            bool(result.grounding_id) and len(rows) == 1
            and rows[0]["model_name"] == "compressibility_predictor"
            and rows[0]["verified"] is True
            and rows[0]["outcome"] == "oracle:compression_roundtrip"
            and rows[0]["sample_fingerprint"], state)

        duplicate = compress(
            content, content_type="text", reversible=True, learn=True
        )
        _ok("identical compression sample is deduplicated across the ledger",
            duplicate.grounding_id == "" and len(_rows()) == 1, state)

        non_reversible = compress(
            "another repeated line\n" * 100,
            content_type="text", reversible=False, learn=True,
        )
        _ok("lossy compression without roundtrip never invents a verified label",
            non_reversible.grounding_id == "" and len(_rows()) == 1, state)

        cache = ResponseCache(tempfile.mkdtemp(), learn=True)
        query = "unique semantic cache oracle query"
        _ok("first cache lookup is a real miss", cache.get(query, model="m") is None,
            state)
        cache.set(query, "cached answer", model="m", tokens_used=9)
        hit = cache.get(query, model="m")
        rows = _rows()
        cache_rows = [
            row for row in rows
            if row["model_name"] == "semantic_cache_hit_predictor"
        ]
        _ok("second cache lookup is a real hit",
            hit is not None and hit.response == "cached answer", state)
        _ok("cache miss and hit become two verified automatic labels",
            len(cache_rows) == 2
            and [row["actual_class"] for row in cache_rows] == [0, 1]
            and all(row["verified"] for row in cache_rows), state)

        ledger = (active_learning.DATA_DIR / "inference_logs.jsonl").read_text(
            encoding="utf-8"
        )
        _ok("oracle ledger stores fingerprints, never raw content or queries",
            content not in ledger and query not in ledger, state)
    finally:
        active_learning.DATA_DIR = original_data_dir
        auto_labels._SEEN_BY_LOG.clear()
        flush_store()

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
