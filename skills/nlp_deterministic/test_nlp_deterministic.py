#!/usr/bin/env python3
"""Tests for nlp_deterministic — classify / extract / keywords (deterministic).

    python -m skills.nlp_deterministic.test_nlp_deterministic
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.nlp_deterministic import classify, extract_entities, keywords


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def main() -> int:
    state = [0, 0]
    print("== nlp_deterministic tests ==")

    intents = {
        "performance": ["fast", "faster", "optimize", "slow", "speed", "latency"],
        "auth": ["login", "password", "token", "authentication", "oauth"],
        "testing": ["test", "tests", "coverage", "pytest", "unit"],
    }

    r = classify("make my SQL queries faster, they are too slow", intents)
    _ok("classify picks 'performance' for a speed task", r["label"] == "performance", state)
    _ok("classify is 0 cloud tokens", r["cloud_tokens"] == 0, state)
    _ok("classify exposes per-label scores", set(r["scores"]) == set(intents), state)

    r2 = classify("add unit tests and improve coverage", intents)
    _ok("classify picks 'testing' for a testing task", r2["label"] == "testing", state)

    r3 = classify("fix the login token authentication flow", intents)
    _ok("classify picks 'auth' for an auth task", r3["label"] == "auth", state)

    # determinism: identical input → identical output
    _ok("classify is deterministic",
        classify("speed up slow code", intents) == classify("speed up slow code", intents),
        state)

    # empty / no intents
    _ok("empty text → no label", classify("", intents)["label"] is None, state)

    # entity extraction
    text = ("see https://example.com/docs and email a@b.io, server 192.168.1.47:6333, "
            "set $API_KEY, run --verbose on ./src/main.py with 42 retries")
    ent = extract_entities(text)
    _ok("extracts urls", "https://example.com/docs" in ent["urls"], state)
    _ok("extracts emails", "a@b.io" in ent["emails"], state)
    _ok("extracts ips", any("192.168.1.47" in x for x in ent["ips"]), state)
    _ok("extracts env vars", "$API_KEY" in ent["env_vars"], state)
    _ok("extracts flags", "--verbose" in ent["flags"], state)
    _ok("extracts paths", any("main.py" in x for x in ent["paths"]), state)
    _ok("extracts numbers", "42" in ent["numbers"], state)
    _ok("extraction is 0 cloud tokens", ent["cloud_tokens"] == 0, state)

    # keywords: stopwords dropped, frequency counted
    kw = keywords("the cache cache cache makes the queries fast and the cache warm")
    words = [k["word"] for k in kw["keywords"]]
    _ok("keywords drops stopwords (no 'the')", "the" not in words, state)
    _ok("keywords ranks the most frequent first", words[0] == "cache", state)
    _ok("keywords is JSON-serialisable + 0 tokens",
        isinstance(json.dumps(kw), str) and kw["cloud_tokens"] == 0, state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
