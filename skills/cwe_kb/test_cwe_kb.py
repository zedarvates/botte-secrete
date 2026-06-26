#!/usr/bin/env python3
"""Tests for cwe_kb — local CWE knowledge base (deterministic, offline).

    python -m skills.cwe_kb.test_cwe_kb
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.cwe_kb import lookup, match, explain, enrich, load_catalog


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def main() -> int:
    state = [0, 0]
    print("== cwe_kb tests ==")

    cat = load_catalog()
    _ok("catalog loads entries", len(cat) >= 10, state)
    _ok("every entry has id/name/description/mitigation",
        all(all(k in e for k in ("id", "name", "description", "mitigation")) for e in cat),
        state)

    # lookup: exact + normalisation + miss
    _ok("lookup CWE-78 → OS Command Injection",
        lookup("CWE-78")["name"] == "OS Command Injection", state)
    _ok("lookup accepts a bare number ('89')", lookup("89")["id"] == "CWE-89", state)
    _ok("lookup unknown → None", lookup("CWE-99999") is None, state)
    _ok("lookup empty → None", lookup("") is None, state)

    # match: embedding ranking (deterministic via hash fallback offline)
    m = match("untrusted user input is concatenated into a SQL query string", top_k=3)
    ids = [x["id"] for x in m["matches"]]
    _ok("match returns ranked CWE ids", len(ids) == 3, state)
    _ok("SQL-flavoured text surfaces CWE-89 in the top matches", "CWE-89" in ids, state)
    _ok("match is deterministic",
        match("eval of user input", top_k=2) == match("eval of user input", top_k=2), state)
    _ok("match is 0 cloud tokens", m["cloud_tokens"] == 0, state)

    # explain: by id wins; falls back to embedding
    _ok("explain by id resolves exactly",
        explain(cwe_id="CWE-502")["resolved_by"] == "id", state)
    _ok("explain without id falls back to embedding matches",
        explain(text="server fetches a user-supplied URL")["resolved_by"] == "embedding", state)

    # enrich: attach context by id, and by embedding when no id
    findings = [
        {"cwe": "CWE-78", "message": "command injection via os.system", "file": "a.py"},
        {"cwe": "", "message": "eval of attacker-controlled expression", "file": "b.py"},
    ]
    enriched = enrich(findings)
    _ok("enrich attaches cwe_info by exact id",
        enriched[0]["cwe_info"]["id"] == "CWE-78"
        and "mitigation" in enriched[0]["cwe_info"], state)
    _ok("enrich resolves a missing id by embedding match",
        enriched[1].get("cwe_info") is not None, state)
    _ok("enrich output is JSON-serialisable",
        isinstance(json.dumps(enriched), str), state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
