#!/usr/bin/env python3
"""Tests for prompt_improver — deterministic parts offline + optional live local.

    python -m skills.prompt_improver.test_prompt_improver
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.prompt_improver import improve, scaffold, StructuredPrompt, PROMPT_SCHEMA_KEYS
from skills.prompt_improver import improver
from skills.llm_backends import registry


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def main() -> int:
    state = [0, 0]
    print("== prompt_improver tests ==")

    # scaffold keeps the raw prompt as the task, 0 tokens.
    sp = scaffold("make my code faster")
    _ok("scaffold puts raw into task", sp.task == "make my code faster", state)
    _ok("scaffold renders markdown with Role/Task",
        "# Role" in sp.to_markdown() and "# Task" in sp.to_markdown(), state)

    # structured dict has exactly the schema keys.
    _ok("to_dict has the canonical schema keys",
        set(sp.to_dict().keys()) == set(PROMPT_SCHEMA_KEYS), state)

    # JSON extraction handles fences + nested braces.
    fenced = '```json\n{"role": "X", "task": "do {y}", "instructions": ["a","b"]}\n```'
    parsed = improver._extract_json(fenced)
    _ok("extract_json strips fences + parses",
        parsed and parsed["role"] == "X" and parsed["instructions"] == ["a", "b"], state)
    _ok("extract_json returns None on garbage", improver._extract_json("no json here") is None, state)

    # coerce normalises types (string → list, drops bad examples).
    coerced = improver._coerce({"task": "t", "constraints": "single", "examples": ["bad", {"input": "i", "output": "o"}]})
    _ok("coerce wraps scalar constraint into list", coerced.constraints == ["single"], state)
    _ok("coerce keeps only dict examples", coerced.examples == [{"input": "i", "output": "o"}], state)

    # improve without local → deterministic scaffold, never fails.
    res = improve("optimize my SQL", use_local=False)
    _ok("no-local improve returns scaffold, 0 cloud tokens",
        res["tier"] == "scaffold" and res["cloud_tokens"] == 0, state)
    _ok("empty prompt → error", "error" in improve("   ", use_local=False), state)

    # JSON mode emits a parseable json_prompt even from scaffold.
    rj = improve("write tests", as_json=True, use_local=False)
    _ok("json mode emits valid json_prompt",
        json.loads(rj["json_prompt"]).get("task") == "write tests", state)

    # optional live: real local rewrite produces a richer structured prompt.
    if registry.best_chat_backend():
        live = improve("rends mon code python plus rapide", as_json=True)
        struct = live["structured"]
        _ok(f"live local rewrite ({live['tier']}) fills role + instructions",
            live["cloud_tokens"] == 0 and bool(struct.get("role"))
            and len(struct.get("instructions", [])) >= 1, state)
    else:
        print("  [skip] live rewrite — no local backend")

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
