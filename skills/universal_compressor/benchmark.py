"""Fixed public fixtures for compression preservation, not LLM answer quality.

Run: python -m skills.universal_compressor.benchmark
Optional installed Headroom 0.37.0: add --headroom --tokens (cache tokenizer first).
No provider call, proxy, agent configuration or training is involved.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.metadata
import json
import os
import platform
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from .compressor import compress


def corpus() -> list[dict]:
    """Version 1: fixed inputs plus narrowly stated protected facts."""
    rows = [{"job": i, "status": "passed", "detail": "synthetic check"} for i in range(80)]
    rows[67] = {"job": 67, "status": "failed", "detail": "FATAL: do not deploy"}
    lines = [f"INFO synthetic step={i} value={i * 3}" for i in range(100)]
    lines[65] = "FATAL commit=fixture-v1: validation failed; do not deploy"
    return [
        {"id": "json_late_error", "type": "json", "input": json.dumps(rows, indent=2),
         "protected": ["FATAL: do not deploy"], "exact": False},
        {"id": "json_long_value", "type": "json", "input": json.dumps({
            "detail": "é漢🙂 " * 180 + "NOT_AUTHORIZED", "status": "PENDING_CI"}, indent=2),
         "protected": ["NOT_AUTHORIZED", "PENDING_CI"], "exact": False},
        {"id": "log_middle_error", "type": "log", "input": "\n".join(lines),
         "protected": [lines[65]], "exact": False},
        {"id": "tool_middle_error", "type": "tool_output", "input": "\n".join(lines),
         "protected": [lines[65]], "exact": False},
        {"id": "code_hash_string", "type": "code", "input": (
            'import os\nurl = "https://example.invalid/a#fragment"\n'
            '# Do not activate this candidate.\nprint(url)\n'),
         "protected": [], "exact": True},
        {"id": "log_exact_repeats", "type": "log", "input": "INFO same synthetic event\n" * 100,
         "protected": ["INFO same synthetic event"], "exact": False},
        {"id": "french_conditions", "type": "text", "input": (
            "Ne pas fusionner. Autorisation absente. Preuve encore incertaine.\n"
            "Activer uniquement après validation indépendante.\n"),
         "protected": ["Ne pas fusionner.", "Autorisation absente.", "Preuve encore incertaine.",
                       "uniquement après validation indépendante."], "exact": False},
    ]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def messages(case: dict) -> list[dict]:
    return [
        {"role": "system", "content": "Report observed facts, uncertainty and authorization limits."},
        {"role": "user", "content": "Inspect this fixture. Preserve failures and conditions."},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "fixture", "type": "function",
         "function": {"name": "read_fixture", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "fixture", "content": case["input"]},
    ]


def botte_arm(value: list[dict], case: dict) -> list[dict]:
    value[-1]["content"] = compress(case["input"], case["type"], learn=False).data
    return value


def assess(case: dict, before: list[dict], after: list[dict]) -> dict:
    """An incomplete envelope or lost protected fact fails even if tokens shrink."""
    envelope_ok = (
        isinstance(after, list) and len(after) == len(before)
        and after[:-1] == before[:-1] and isinstance(after[-1], dict)
        and {k: v for k, v in after[-1].items() if k != "content"}
        == {k: v for k, v in before[-1].items() if k != "content"}
        and isinstance(after[-1].get("content"), str)
    )
    data = after[-1]["content"] if envelope_ok else ""
    missing = [fact for fact in case["protected"] if fact not in data]
    exact_ok = not case["exact"] or data == case["input"]
    return {"passed": envelope_ok and not missing and exact_ok,
            "envelope_preserved": envelope_ok, "missing_protected": missing,
            "exact_required": case["exact"], "exact_passed": exact_ok}


def run(arms: dict | None = None, token_counter=None) -> dict:
    selected = arms if arms is not None else {"original": lambda value, case: value, "botte": botte_arm}
    cases = corpus()
    rows = []
    for case in cases:
        before = messages(case)
        raw = json.dumps(before, ensure_ascii=False, separators=(",", ":"))
        for name, arm in selected.items():
            start = time.perf_counter_ns()
            after = arm(copy.deepcopy(before), case)
            elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000
            rendered = json.dumps(after, ensure_ascii=False, separators=(",", ":"))
            rows.append({
                "case": case["id"], "arm": name, "gate": assess(case, before, after),
                "input_sha256": sha256(raw.encode("utf-8")),
                "output_sha256": sha256(rendered.encode("utf-8")),
                "input_bytes": len(raw.encode("utf-8")), "output_bytes": len(rendered.encode("utf-8")),
                "input_tokens": token_counter(raw) if token_counter else None,
                "output_tokens": token_counter(rendered) if token_counter else None,
                "elapsed_ms": round(elapsed_ms, 3), "messages": after,
            })
    return {"schema": "botte.compression-fixtures/v1", "corpus": cases,
            "corpus_sha256": sha256(json.dumps(cases, ensure_ascii=False, sort_keys=True).encode("utf-8")),
            "source_sha256": sha256(Path(__file__).with_name("compressor.py").read_bytes()),
            "harness_sha256": sha256(Path(__file__).read_bytes()),
            "python": platform.python_version(), "rows": rows,
            "measurement": "UTF-8 bytes; optional tokens of serialized messages, not provider usage",
            "llm_calls": 0, "model_quality": "not_evaluated", "headroom": {"status": "not_run"}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--headroom", action="store_true", help="Use installed headroom-ai==0.37.0")
    parser.add_argument("--tokens", action="store_true", help="Use cached tiktoken o200k_base")
    args = parser.parse_args(argv)
    env = {"HEADROOM_OFFLINE": "1", "HEADROOM_BEACON": "off", "HEADROOM_TELEMETRY": "off",
           "DO_NOT_TRACK": "1", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
           "HEADROOM_CCR_BACKEND": "memory", "BOTTE_NN_AUTO_LABELS": "0",
           "LITELLM_LOCAL_MODEL_COST_MAP": "True"}
    arms = {"original": lambda value, case: value, "botte": botte_arm}
    counter = None
    tokenizer = {"status": "not_measured"}
    headroom = {"status": "not_run"}
    # Scope Python network denial and Headroom state to this CLI invocation.
    # Native extensions are governed by their offline flags, not this Python patch.
    with tempfile.TemporaryDirectory(prefix="botte-compression-") as tmp, patch.dict(
        os.environ, {**env, "HEADROOM_WORKSPACE_DIR": tmp, "HEADROOM_CONFIG_DIR": tmp}
    ), patch("socket.socket.connect", side_effect=RuntimeError("benchmark network disabled")):
        if args.tokens:
            import tiktoken
            encoding = tiktoken.get_encoding("o200k_base")
            counter = lambda value: len(encoding.encode(value, disallowed_special=()))
            tokenizer = {"status": "measured", "name": encoding.name,
                         "library": "tiktoken", "version": importlib.metadata.version("tiktoken")}
        if args.headroom:
            version = importlib.metadata.version("headroom-ai")
            if version != "0.37.0":
                parser.error("This fixture adapter is pinned to headroom-ai==0.37.0")
            from headroom import compress as headroom_compress
            config = {"compress_system_messages": False, "protect_recent": 0,
                      "frozen_message_count": 3, "kompress_model": "disabled"}
            arms["headroom"] = lambda value, case: headroom_compress(value, model="gpt-4o", **config).messages
            headroom = {"status": "executed", "version": version, "config": config,
                        "package_record_sha256": sha256(importlib.metadata.distribution("headroom-ai")
                                                        .read_text("RECORD").encode("utf-8")),
                        "recovery_loop": "not_evaluated"}
        report = run(arms, counter)
        if args.headroom:
            from headroom.ccr.marker_resolution import resolve_markers_in_response
            cases = {case["id"]: case for case in report["corpus"]}
            for row in report["rows"]:
                if row["arm"] != "headroom" or row["gate"]["passed"]:
                    continue
                case = cases[row["case"]]
                recovered = copy.deepcopy(row["messages"])
                try:
                    value = recovered[-1]["content"]
                    if case["type"] == "json":
                        value = json.dumps(resolve_markers_in_response(json.loads(value)),
                                           ensure_ascii=False, separators=(",", ":"))
                    else:
                        value = resolve_markers_in_response(value)
                    recovered[-1]["content"] = value
                    rendered = json.dumps(recovered, ensure_ascii=False, separators=(",", ":"))
                    row["recovery_probe"] = {
                        "gate": assess(case, messages(case), recovered), "messages": recovered,
                        "output_tokens": counter(rendered) if counter else None,
                        "output_bytes": len(rendered.encode("utf-8")),
                        "method": "deterministic inline resolution; no model retrieval decision",
                    }
                except (TypeError, ValueError, KeyError) as exc:
                    row["recovery_probe"] = {"error": type(exc).__name__}
            headroom["recovery_loop"] = "failed-row deterministic probe only; LLM loop not evaluated"
    report["headroom"] = headroom
    report["tokenizer"] = tokenizer
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(row["gate"]["passed"] for row in report["rows"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
