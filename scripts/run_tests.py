#!/usr/bin/env python3
"""Run every Botte Secrète test suite and report a single total.

    python scripts/run_tests.py

Cross-platform: forces UTF-8 + PYTHONPATH for child processes, so it works on a
default Windows console too. Exit code is non-zero if any suite fails.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# (label, command) — the e2e script + every module's test_<module>.
SUITES = [
    ("e2e", [sys.executable, "skills/test_e2e.py"]),
    ("llm_backends", [sys.executable, "-m", "skills.llm_backends.test_llm_backends"]),
    ("directives_audit", [sys.executable, "-m", "skills.directives_audit.test_directives_audit"]),
    ("auto_router", [sys.executable, "-m", "skills.auto_router.test_auto_router"]),
    ("skill_finder", [sys.executable, "-m", "skills.skill_finder.test_skill_finder"]),
    ("bootstrap", [sys.executable, "-m", "skills.bootstrap.test_bootstrap"]),
    ("infra_advisor", [sys.executable, "-m", "skills.infra_advisor.test_infra_advisor"]),
    ("prompt_improver", [sys.executable, "-m", "skills.prompt_improver.test_prompt_improver"]),
    ("metrics", [sys.executable, "-m", "skills.metrics.test_metrics"]),
    ("preflight", [sys.executable, "-m", "skills.preflight.test_preflight"]),
    ("checkup", [sys.executable, "-m", "skills.checkup.test_checkup"]),
    ("ingest", [sys.executable, "-m", "skills.ingest.test_ingest"]),
    ("docgen", [sys.executable, "-m", "skills.docgen.test_docgen"]),
    ("app_test", [sys.executable, "-m", "skills.app_test.test_app_test"]),
    ("capabilities", [sys.executable, "-m", "skills.capabilities.test_capabilities"]),
    ("cluster", [sys.executable, "-m", "skills.cluster.test_cluster"]),
    ("fallow_scanner", [sys.executable, "-m", "skills.fallow_like.test_scanner"]),
]

_RESULT_RE = re.compile(r"(\d+)\s+passed,\s+(\d+)\s+failed")
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        rc = getattr(s, "reconfigure", None)
        if rc:
            try:
                rc(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass

    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
           "PYTHONPATH": str(REPO)}
    total_pass = total_fail = 0
    rows = []
    for label, cmd in SUITES:
        proc = subprocess.run(cmd, cwd=REPO, env=env, capture_output=True,
                               text=True, encoding="utf-8", errors="replace")
        m = None
        for line in (proc.stdout or "").splitlines():
            mm = _RESULT_RE.search(_ANSI_RE.sub("", line))
            if mm:
                m = mm
        p, f = (int(m.group(1)), int(m.group(2))) if m else (0, 1)
        if not m and proc.returncode != 0:
            f = max(f, 1)
        total_pass += p
        total_fail += f
        mark = "OK " if f == 0 and (m or proc.returncode == 0) else "FAIL"
        rows.append(f"  [{mark}] {label:<18} {p} passed, {f} failed")

    print("Botte Secrète — test suites\n")
    print("\n".join(rows))
    print(f"\nTOTAL: {total_pass} passed, {total_fail} failed")
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
