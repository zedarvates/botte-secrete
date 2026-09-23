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
        _ok("exact-only lookups never label the semantic predictor",
            not cache_rows, state)

        source_query = "alpha beta gamma delta epsilon"
        semantic_query = "alpha beta gamma delta epsilon extra"
        semantic_miss_query = "unrelated lookup with different vocabulary"
        cache.set(source_query, "semantic answer", model="m", tokens_used=7)
        semantic_hit = cache.get(semantic_query, use_semantic=True, model="m")
        semantic_miss = cache.get(
            semantic_miss_query, use_semantic=True, model="m"
        )
        cache_rows = [
            row for row in _rows()
            if row["model_name"] == "semantic_cache_hit_predictor"
        ]
        _ok("semantic lookup exercises one observed hit and one observed miss",
            semantic_hit is not None and semantic_hit.response == "semantic answer"
            and semantic_miss is None, state)
        _ok("only semantic attempts become verified automatic labels",
            len(cache_rows) == 2
            and [row["actual_class"] for row in cache_rows] == [1, 0]
            and [row["outcome"] for row in cache_rows] == [
                "oracle:response_cache_semantic_hit",
                "oracle:response_cache_semantic_miss",
            ]
            and all(row["verified"] for row in cache_rows), state)
        _ok("semantic history excludes exact-only lookups",
            [row["features"][5] for row in cache_rows] == [0.0, 1.0]
            and cache.report()["semantic_attempts"] == 2
            and cache.report()["semantic_hit_rate_pct"] == 50, state)
        _ok("semantic observations use discriminating pre-match features",
            cache_rows[0]["features"][3] > cache_rows[1]["features"][3]
            and cache_rows[0]["features"][1:5] != [0.5, 0.5, 1.0, 0.5]
            and cache_rows[0]["features"] != cache_rows[1]["features"], state)

        shadow_cache = ResponseCache(
            tempfile.mkdtemp(), learn=True, semantic_shadow=True
        )
        shadow_source = "red green blue yellow orange"
        shadow_hit_query = "red green blue yellow orange violet"
        shadow_miss_query = "circle square triangle hexagon pentagon"
        shadow_cache.set(
            shadow_source, "must never be served", model="m", tokens_used=11
        )
        shadow_hit_result = shadow_cache.get(shadow_hit_query, model="m")
        shadow_miss_result = shadow_cache.get(shadow_miss_query, model="m")
        shadow_rows = [
            row for row in _rows()
            if row["outcome"].startswith("oracle:response_cache_semantic_shadow_")
        ]
        shadow_report = shadow_cache.report()
        source_entry = shadow_cache._entries[
            shadow_cache._hash(shadow_source, model="m")
        ]
        _ok("shadow mode observes candidates without serving cached responses",
            shadow_hit_result is None and shadow_miss_result is None
            and source_entry.hit_count == 0, state)
        _ok("shadow accounting never claims served hits or token savings",
            shadow_report["hits_semantic"] == 0
            and shadow_report["tokens_saved_total"] == 0
            and shadow_report["semantic_served_attempts"] == 0
            and shadow_report["semantic_shadow_attempts"] == 2, state)
        _ok("shadow attempts produce auditable conditional labels",
            len(shadow_rows) == 2
            and [row["actual_class"] for row in shadow_rows] == [1, 0]
            and [row["features"][5] for row in shadow_rows] == [0.0, 1.0]
            and all(row["verified"] for row in shadow_rows), state)

        context_cache = ResponseCache(tempfile.mkdtemp())
        context_source = "secure alpha beta gamma delta"
        context_query = "secure alpha beta gamma delta epsilon"
        context_cache.set(
            context_source, "context-a only", model="m", context="system-a"
        )
        wrong_context = context_cache.get(
            context_query, use_semantic=True, model="m", context="system-b"
        )
        right_context = context_cache.get(
            context_query, use_semantic=True, model="m", context="system-a"
        )
        persisted_context_cache = context_cache.cache_file.read_text(
            encoding="utf-8"
        )
        _ok("semantic candidates never cross model/system context boundaries",
            wrong_context is None and right_context is not None
            and right_context.response == "context-a only", state)
        _ok("cache persists only the system-context fingerprint",
            "system-a" not in persisted_context_cache
            and context_cache._context_hash("system-a") in persisted_context_cache,
            state)
        wrong_context_features = context_cache._grounding_values(
            context_query, model="m", context="system-b"
        )
        right_context_features = context_cache._grounding_values(
            context_query, model="m", context="system-a"
        )
        _ok("grounding summaries respect model/system context boundaries",
            wrong_context_features["eligible_cache_density"] == 0.0
            and right_context_features["eligible_cache_density"] > 0.0
            and wrong_context_features["eligible_vocabulary_coverage"] == 0.0
            and right_context_features["eligible_vocabulary_coverage"] > 0.0,
            state)

        collision_rows = [
            active_learning.InferenceLog(
                model_name="semantic_cache_hit_predictor",
                features=[0.1] * 7,
                predicted_class=index % 2,
                actual_class=index % 2,
                correct=True,
                verified=True,
            )
            for index in range(50)
        ]
        collision_report = active_learning.feature_label_collision_report(
            collision_rows
        )
        _ok("collision audit detects contradictory labels without exposing features",
            collision_report == {
                "verified_rows": 50,
                "feature_groups": 1,
                "contradictory_groups": 1,
                "contradictory_rows": 50,
                "contradictory_rate": 1.0,
            }, state)
        learner = active_learning.ActiveLearning()
        learner.logs["semantic_cache_hit_predictor"] = collision_rows
        _ok("contradictory semantic evidence cannot update model weights",
            learner.train(
                "semantic_cache_hit_predictor", epochs=1, verbose=False
            ) is None, state)

        invalid_outcome_rejected = 0
        for invalid_hit, invalid_kind in (
            (True, "exact_hit"),
            (False, "semantic_hit"),
        ):
            try:
                auto_labels.record_cache_lookup(
                    "invalid cache outcome",
                    cache._grounding_values("invalid cache outcome"),
                    hit=invalid_hit, hit_kind=invalid_kind,
                )
            except ValueError:
                invalid_outcome_rejected += 1
        _ok("label API rejects exact hits and inconsistent semantic outcomes",
            invalid_outcome_rejected == 2, state)

        ledger = (active_learning.DATA_DIR / "inference_logs.jsonl").read_text(
            encoding="utf-8"
        )
        _ok("oracle ledger stores fingerprints, never raw content or queries",
            content not in ledger and query not in ledger
            and semantic_query not in ledger and semantic_miss_query not in ledger
            and shadow_hit_query not in ledger and shadow_miss_query not in ledger,
            state)
    finally:
        active_learning.DATA_DIR = original_data_dir
        auto_labels._SEEN_BY_LOG.clear()
        flush_store()

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
