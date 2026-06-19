#!/usr/bin/env python3
"""Tests for app_test — spec validation + deterministic script generation.

(End-to-end GUI runs need SikuliX + a display + the app, so they're out of scope
here; we test the generator and the spec contract, which are deterministic.)

    python -m skills.app_test.test_app_test
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

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

        # run() always generates; reports gracefully if SikuliX absent
        r = run(sp, out_dir=d)
        _ok("run() generates the script and reports SikuliX status",
            "script" in r and ("ran" in r), state)

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
