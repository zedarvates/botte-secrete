#!/usr/bin/env python3
"""Tests for docgen — offline-deterministic + guarded live (local LLM).

    python -m skills.docgen.test_docgen
"""

from __future__ import annotations

import contextlib
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.docgen import draft_doc, session_review
from skills.docgen.docgen import _load_transcript


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


@contextlib.contextmanager
def _stub_local_llm(answer: str):
    """Deterministic local LLM: canned reply + backend forced reachable.

    The model's output is non-deterministic (and can time out), so the live LLM
    path is exercised against a stub instead — the suite stays green regardless
    of which local model is loaded. Patches the shared client class so every
    import style (top-level or in-function) sees it.
    """
    import skills.llm_backends.client as _c
    import skills.llm_backends.registry as _r
    o_chat, o_init, o_best = (_c.LocalLLMClient.chat, _c.LocalLLMClient.__init__,
                              _r.best_chat_backend)
    _c.LocalLLMClient.__init__ = lambda self, *a, **k: None
    _c.LocalLLMClient.chat = lambda self, *a, **k: type("_R", (), {"text": answer})()
    _r.best_chat_backend = lambda *a, **k: object()
    try:
        yield
    finally:
        _c.LocalLLMClient.chat, _c.LocalLLMClient.__init__ = o_chat, o_init
        _r.best_chat_backend = o_best


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

    # local LLM path — deterministic via a stubbed local client
    with _stub_local_llm('{"done":["built metrics"],"decisions":[],'
                         '"learnings":[],"next":[]}'):
        r = draft_doc("how to add two numbers in python", kind="guide", max_tokens=300)
        _ok("draft_doc produces a local-first doc (0 cloud)",
            bool(r.get("doc") or r.get("draft")) and "error" not in r, state)
        _ok("draft is marked drafted_locally", r.get("drafted_locally") is True, state)

        rev = session_review(
            "user: build metrics module\nassistant: built it, 125 tests pass",
            is_file=False, max_tokens=300)
        _ok("session_review returns a review at 0 cloud tokens",
            rev.get("cloud_tokens") == 0 and "review" in rev, state)

    # graceful degradation when there is no local backend at all
    import skills.llm_backends.registry as _reg
    _saved = _reg.best_chat_backend
    _reg.best_chat_backend = lambda *a, **k: None
    try:
        _ok("session_review degrades gracefully without backend",
            "error" in session_review("x", is_file=False), state)
    finally:
        _reg.best_chat_backend = _saved

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
