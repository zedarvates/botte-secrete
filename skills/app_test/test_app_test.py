#!/usr/bin/env python3
"""Tests for app_test — spec validation + deterministic script generation.

(End-to-end GUI runs need SikuliX + a display + the app, so they're out of scope
here; we test the generator and the spec contract, which are deterministic.)

    python -m skills.app_test.test_app_test
"""

from __future__ import annotations

import json
import io
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.app_test.generator import load_spec, to_sikulix_script, write_script, run


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


SPEC = {
    "name": "login_flow", "image_dir": "imgs", "similarity": 0.85,
    "steps": [
        {"do": "wait", "image": "login.png", "timeout": 5},
        {"do": "click", "image": "login.png"},
        {"do": "type", "text": 'he said "hi"'},
        {"do": "assert_visible", "image": "welcome.png"},
        {"do": "assert_absent", "image": "error.png"},
    ],
}


def main() -> int:
    state = [0, 0]
    print("== app_test tests ==")

    with tempfile.TemporaryDirectory() as d:
        sp = Path(d) / "spec.json"
        sp.write_text(json.dumps(SPEC), encoding="utf-8")
        spec = load_spec(sp)
        _ok("valid spec loads", spec["name"] == "login_flow", state)

        script = to_sikulix_script(spec)
        _ok("script sets similarity", "Settings.MinSimilarity = 0.85" in script, state)
        _ok("script clicks the image with image_dir prefix", 'click("imgs/login.png")' in script, state)
        _ok("script escapes quotes in typed text", 'type("he said \\"hi\\"")' in script, state)
        _ok("script has assert_visible + assert_absent",
            'exists("imgs/welcome.png"' in script and 'still visible imgs/error.png' in script, state)
        _ok("script exits non-zero on errors", "sys.exit(1 if errors else 0)" in script, state)

        # write bundle
        bundle = write_script(spec, d)
        _ok("writes a .sikuli bundle with a .py",
            bundle.suffix == ".sikuli" and (bundle / "login_flow.py").exists(), state)

        # run() always generates; reports gracefully when no runner is found
        # (force the no-runner path so the unit test never launches a GUI).
        import skills.app_test.generator as gen
        _orig = gen.find_sikulix
        gen.find_sikulix = lambda: None
        try:
            r = run(sp, out_dir=d)
        finally:
            gen.find_sikulix = _orig
        _ok("run() generates the script + reports runner-absent gracefully",
            r.get("ran") is False and r.get("status") == "not_run"
            and r.get("passed") is False and Path(r["script"]).exists(), state)

    # artifacts: step parsing, log tailing, HTML report
    from skills.app_test import artifacts as art
    out = ("[log] TYPE x\nSTEP 0 OK: visible a.png\nSTEP 1 FAIL: click b.png\n"
           "RESULT: 1 errors\n")
    steps = art.parse_steps(out)
    _ok("parse_steps reads OK/FAIL markers",
        len(steps) == 2 and steps[1]["status"] == "FAIL", state)
    with tempfile.TemporaryDirectory() as d:
        lg = Path(d) / "crash.log"; lg.write_text("line1\nboom\n", encoding="utf-8")
        logs = art.collect_logs([str(lg), str(Path(d) / "missing.log")])
        _ok("collect_logs tails existing + marks missing",
            "boom" in logs[str(lg)] and "not found" in logs[str(Path(d) / "missing.log")], state)
        rpt = art.html_report("demo", output=out, steps=steps, logs=logs,
                              out_path=Path(d) / "r.html")
        htmltxt = rpt.read_text(encoding="utf-8")
        _ok("html_report writes a verdict + steps + logs",
            "FAIL (1)" in htmltxt and "click b.png" in htmltxt and "boom" in htmltxt, state)

    # Verdicts require coherent execution evidence. These transcripts model the
    # runner contract only; neither these tests nor their mocks drive a GUI.
    cases = [
        ("empty output", "", 0, "incomplete"),
        ("crash without markers", "runner crashed\n", 0, "incomplete"),
        ("nonzero exit with zero errors", "RESULT: 0 errors\n", 1, "failed"),
        ("failed step with zero errors", "STEP 0 FAIL: type\nRESULT: 0 errors\n", 0, "failed"),
        ("failed step without result", "STEP 0 FAIL: click\n", 0, "failed"),
        ("positive result", "RESULT: 1 errors\n", 0, "failed"),
        ("conflicting results", "RESULT: 1 errors\nRESULT: 0 errors\n", 0, "failed"),
        ("duplicate zero results", "RESULT: 0 errors\nRESULT: 0 errors\n", 0, "incomplete"),
        ("embedded result", "[log] RESULT: 0 errors\n", 0, "incomplete"),
        ("trailing result text", "RESULT: 0 errors ignored\n", 0, "incomplete"),
        ("oversized result count", "RESULT: " + "9" * 4301 + " errors\n", 0, "incomplete"),
        ("oversized failing step index", "STEP " + "9" * 4301 + " FAIL: click\nRESULT: 0 errors\n", 0, "failed"),
        ("unknown exit", "RESULT: 0 errors\n", None, "incomplete"),
        ("complete action-only run", "RESULT: 0 errors\n", 0, "passed"),
        ("complete assertion run", "STEP 0 OK: visible a.png\nRESULT: 0 errors\n", 0, "passed"),
        ("Windows transcript", "STEP 0 OK: visible a.png\r\nRESULT: 0 errors\r\n", 0, "passed"),
    ]
    for label, output, exit_code, expected in cases:
        verdict = art.evaluate_run(output, exit_code=exit_code)
        _ok(f"verdict: {label}", verdict["status"] == expected
            and verdict["passed"] is (expected == "passed"), state)
    huge_steps = art.parse_steps("STEP " + "9" * 4301 + " FAIL: click\n")
    _ok("oversized step index is omitted without losing failure evidence",
        huge_steps == [{"index": None, "index_omitted": True,
                        "status": "FAIL", "detail": "click"}], state)

    with tempfile.TemporaryDirectory() as d:
        sp = Path(d) / "spec.json"
        sp.write_text(json.dumps(SPEC), encoding="utf-8")
        for label, output, exit_code, expected in cases:
            if exit_code is None:
                continue
            proc = subprocess.CompletedProcess([], exit_code, output, "")
            with patch.object(gen, "find_sikulix", return_value="test-runner"), \
                    patch.object(gen.subprocess, "run", return_value=proc):
                result = run(sp, out_dir=d)
            text = Path(result["report"]).read_text(encoding="utf-8")
            title = {"passed": "PASS", "failed": "FAIL", "incomplete": "INCOMPLETE"}[expected]
            _ok(f"API and HTML agree: {label}", result["status"] == expected
                and result["passed"] is (expected == "passed")
                and f'<span class="v">{title}' in text, state)

        with patch.object(gen, "find_sikulix", return_value="test-runner"), \
                patch.object(gen.subprocess, "run", side_effect=OSError("cannot start")):
            result = run(sp, out_dir=d)
        _ok("launch error is not_run", result["status"] == "not_run"
            and result["ran"] is False and result["passed"] is False, state)
        with patch.object(gen, "find_sikulix", return_value="test-runner"), \
                patch.object(gen.subprocess, "run", side_effect=subprocess.TimeoutExpired([], 600)):
            result = run(sp, out_dir=d)
        _ok("timeout is incomplete", result["status"] == "incomplete"
            and result["ran"] is True and result["passed"] is False, state)

        rpt = art.html_report("unknown-exit", output="RESULT: 0 errors\n",
                              out_path=Path(d) / "standalone.html")
        _ok("standalone HTML needs observed exit code",
            '<span class="v">INCOMPLETE</span>' in rpt.read_text(encoding="utf-8"), state)
        rpt = art.html_report("not-started", output="", ran=False,
                              out_path=Path(d) / "not-run.html")
        _ok("HTML can report not_run",
            '<span class="v">NOT RUN</span>' in rpt.read_text(encoding="utf-8"), state)
        rpt = art.html_report("supplied-failure", output="RESULT: 0 errors\n", exit_code=0,
                              steps=[{"index": 0, "status": "FAIL", "detail": "provided failure"}],
                              out_path=Path(d) / "supplied-failure.html")
        _ok("supplied failure rows cannot produce HTML PASS",
            '<span class="v">FAIL (1)</span>' in rpt.read_text(encoding="utf-8"), state)
        _ok("supplied empty steps cannot hide output failures",
            art.evaluate_run("STEP 0 FAIL: click\nRESULT: 0 errors\n", exit_code=0,
                             steps=[])["status"] == "failed", state)

    from skills.app_test import cli
    for status, ran, passed, expected in (("passed", True, True, 0),
                                         ("failed", True, False, 1),
                                         ("incomplete", True, False, 2),
                                         ("not_run", False, False, 2)):
        with patch.object(cli, "run", return_value={"status": status, "ran": ran, "passed": passed}), \
                redirect_stdout(io.StringIO()):
            code = cli.main(["run", "unused.json"])
        _ok(f"CLI exit reflects {status}", code == expected, state)

    # invalid specs rejected
    for bad in ({"steps": [{"do": "frobnicate"}]},
                {"steps": [{"do": "click"}]},          # missing image
                {"steps": [{"do": "type"}]}):          # missing text
        with tempfile.TemporaryDirectory() as d:
            sp = Path(d) / "b.json"; sp.write_text(json.dumps(bad), encoding="utf-8")
            try:
                load_spec(sp); ok = False
            except ValueError:
                ok = True
            _ok(f"rejects invalid spec ({bad['steps'][0].get('do')})", ok, state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
