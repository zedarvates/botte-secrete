#!/usr/bin/env python3
"""Tests for completion_proof — policy A11 detector (hermetic).

    python -m skills.completion_proof.test_completion_proof
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from skills.completion_proof import audit_path
from skills.console_utf8 import force_utf8


def _ok(msg, cond, state):
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    state[0 if cond else 1] += 1


def main() -> int:
    state = [0, 0]
    force_utf8()
    print("== completion_proof tests ==")

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        reports = root / "reports"
        reports.mkdir()

        bare = reports / "audit-report.json"
        bare.write_text(json.dumps({"status": "complete", "v": "TERMINÉ"}),
                        encoding="utf-8")

        proven = reports / "fix-report.json"
        proven.write_text(json.dumps({
            "status": "complete",
            "proof": {"test_id": "skills.code_complexity.test_code_complexity"},
        }), encoding="utf-8")

        agent = reports / "agent-state.json"
        agent.write_text(json.dumps({
            "state": "completed",
            "completion": {
                "changed_paths": ["x.py"],
                "validations": [{
                    "name": "unit",
                    "status": "passed",
                    "reference": "exit_code=0; git=abc1234; snapshot=deadbeefcafebabe",
                }],
                "residual_risk": "none",
                "revision": 1,
            },
        }), encoding="utf-8")

        md_bare = reports / "summary.md"
        md_bare.write_text("# Status: complete\nAll checks passed\n", encoding="utf-8")

        md_proven = reports / "verified.md"
        md_proven.write_text(
            "status: complete\nRESULT: 12 passed, 0 failed\n", encoding="utf-8")

        jsonl = reports / "events.jsonl"
        jsonl.write_text(
            json.dumps({"kind": "route", "out": "local"}) + "\n"
            + json.dumps({"status": "done"}) + "\n"
            + json.dumps({"status": "done", "artifact_hash": "abc123def4567890"}) + "\n",
            encoding="utf-8")

        ignored = reports / "notes.txt"
        ignored.write_text("hello world, nothing finished here\n", encoding="utf-8")

        r = audit_path(reports)
        locs = {f["f"] for f in r["findings"]}

        _ok("bare JSON completion is flagged",
            any("audit-report.json" in loc for loc in locs), state)
        _ok("JSON with test_id proof is NOT flagged",
            all("fix-report.json" not in loc for loc in locs), state)
        _ok("agent_state completion with passed validation is NOT flagged",
            all("agent-state.json" not in loc for loc in locs), state)
        _ok("markdown claim without proof is flagged",
            any("summary.md" in loc for loc in locs), state)
        _ok("markdown claim with 'N passed' is NOT flagged",
            all("verified.md" not in loc for loc in locs), state)
        _ok("jsonl line without proof is flagged, proven line is not",
            any("events.jsonl:2" in loc for loc in locs)
            and all("events.jsonl:3" not in loc for loc in locs)
            and all("events.jsonl:1" not in loc for loc in locs), state)
        _ok("neutral text is not flagged",
            all("notes.txt" not in loc for loc in locs), state)

        g = next(f for f in r["findings"] if "audit-report.json" in f["f"])
        _ok("finding carries the five policy fields",
            all(k in g for k in ("preuve", "cout_estime", "gain_attendu",
                                 "risque", "refactoring_minimal")), state)
        _ok("result is JSON-serialisable", isinstance(json.dumps(r), str), state)
        _ok("cloud_tokens is zero", r["cloud_tokens"] == 0, state)

        missing = audit_path(root / "nope")
        _ok("missing path → error", "error" in missing, state)

        solo = audit_path(proven)
        _ok("single proven file → empty findings", solo["findings"] == [], state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
