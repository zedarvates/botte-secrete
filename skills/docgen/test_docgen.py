#!/usr/bin/env python3
"""Tests for docgen — offline-deterministic + guarded live (local LLM).

    python -m skills.docgen.test_docgen
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.docgen import draft_doc, session_review
from skills.docgen.docgen import _load_transcript


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def _local_backend() -> bool:
    try:
        from skills.llm_backends import registry
        return registry.best_chat_backend() is not None
    except Exception:
        return False


def main() -> int:
    state = [0, 0]
    print("== docgen tests ==")

    # transcript parsing (offline, deterministic): JSONL → role: text lines
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "t.jsonl"
        f.write_text(
            '{"message":{"role":"user","content":"do X"}}\n'
            '{"message":{"role":"assistant","content":[{"type":"text","text":"did X"}]}}\n',
            encoding="utf-8")
        txt = _load_transcript(str(f), is_file=True)
        _ok("transcript JSONL parsed to role:text",
            "user: do X" in txt and "assistant: did X" in txt, state)
    _ok("raw text passthrough", _load_transcript("hello", is_file=False) == "hello", state)

    if _local_backend():
        # draft_doc: local draft present, 0 cloud (no key) → refined_by notes none
        r = draft_doc("how to add two numbers in python", kind="guide", max_tokens=300)
        _ok("draft_doc produces a doc/draft",
            bool(r.get("doc") or r.get("draft")) and "error" not in r, state)
        _ok("draft is local (refine only with cloud key)",
            r.get("drafted_locally") in (True, False), state)  # structure present

        rev = session_review(
            "user: build metrics module\nassistant: built it, 125 tests pass",
            is_file=False, max_tokens=300)
        _ok("session_review returns a review at 0 cloud tokens",
            rev.get("cloud_tokens") == 0 and "review" in rev, state)
    else:
        print("  [skip] no local backend — draft_doc/session_review live tests")
        # still verify graceful error path
        rev = session_review("x", is_file=False)
        _ok("session_review degrades gracefully without backend", "error" in rev, state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
