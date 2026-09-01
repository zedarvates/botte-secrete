#!/usr/bin/env python3
"""Run every Botte Secrète test suite and report a single total.

    python scripts/run_tests.py                  # all suites
    python scripts/run_tests.py --changed         # only suites for changed files
    python scripts/run_tests.py -q                # quiet: one line per suite (detail on failure)
    python scripts/run_tests.py --changed -q      # both

Cross-platform: forces UTF-8 + PYTHONPATH for child processes, so it works on a
default Windows console too. Exit code is non-zero if any suite fails.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from skills.atomic_json import write_json

# Test traffic must never inflate the user's production grounding ledger.
os.environ.setdefault("BOTTE_NN_AUTO_LABELS", "0")

# (label, command, module_prefix) — the e2e script + every module's test_<module>.
# module_prefix is the skills/ directory prefix used for --changed matching.
SUITES = [
    ("e2e", [sys.executable, "skills/test_e2e.py"], ""),
    ("cli_router", [sys.executable, "-m", "skills.test_cli"], "skills/"),
    ("llm_backends", [sys.executable, "-m", "skills.llm_backends.test_llm_backends"], "skills/llm_backends/"),
    ("directives_audit", [sys.executable, "-m", "skills.directives_audit.test_directives_audit"], "skills/directives_audit/"),
    ("auto_router", [sys.executable, "-m", "skills.auto_router.test_auto_router"], "skills/auto_router/"),
    ("router_outcome", [sys.executable, "-m", "skills.auto_router.test_outcome_adapter"], "skills/auto_router/"),
    ("skill_finder", [sys.executable, "-m", "skills.skill_finder.test_skill_finder"], "skills/skill_finder/"),
    ("project_profiler", [sys.executable, "-m", "skills.skill_project_optimizer.test_profiler"], "skills/skill_project_optimizer/"),
    ("bootstrap", [sys.executable, "-m", "skills.bootstrap.test_bootstrap"], "skills/bootstrap/"),
    ("infra_advisor", [sys.executable, "-m", "skills.infra_advisor.test_infra_advisor"], "skills/infra_advisor/"),
    ("prompt_improver", [sys.executable, "-m", "skills.prompt_improver.test_prompt_improver"], "skills/prompt_improver/"),
    ("metrics", [sys.executable, "-m", "skills.metrics.test_metrics"], "skills/metrics/"),
    ("preflight", [sys.executable, "-m", "skills.preflight.test_preflight"], "skills/preflight/"),
    ("checkup", [sys.executable, "-m", "skills.checkup.test_checkup"], "skills/checkup/"),
    ("ingest", [sys.executable, "-m", "skills.ingest.test_ingest"], "skills/ingest/"),
    ("docgen", [sys.executable, "-m", "skills.docgen.test_docgen"], "skills/docgen/"),
    ("app_test", [sys.executable, "-m", "skills.app_test.test_app_test"], "skills/app_test/"),
    ("capabilities", [sys.executable, "-m", "skills.capabilities.test_capabilities"], "skills/capabilities/"),
    ("cluster", [sys.executable, "-m", "skills.cluster.test_cluster"], "skills/cluster/"),
    ("conductor", [sys.executable, "-m", "skills.conductor.test_conductor"], "skills/conductor/"),
    ("control_loop", [sys.executable, "-m", "skills.control_loop.test_control_loop"], "skills/control_loop/"),
    ("report", [sys.executable, "-m", "skills.report.test_report"], "skills/report/"),
    ("cost_estimator", [sys.executable, "-m", "skills.cost_estimator.test_cost_estimator"], "skills/cost_estimator/"),
    ("trends", [sys.executable, "-m", "skills.trends.test_trends"], "skills/trends/"),
    ("dashboard", [sys.executable, "-m", "skills.dashboard.test_dashboard"], "skills/dashboard/"),
    ("quality_dashboard", [sys.executable, "-m", "skills.dashboard.test_quality_compass"], "skills/dashboard/"),
    ("fallow_scanner", [sys.executable, "-m", "skills.fallow_like.test_scanner"], "skills/fallow_like/"),
    ("dead_code", [sys.executable, "-m", "skills.fallow_like.test_dead_code"], "skills/fallow_like/"),
    ("taint", [sys.executable, "-m", "skills.fallow_like.test_taint"], "skills/fallow_like/"),
    ("docs_steward", [sys.executable, "-m", "skills.docs_steward.test_docs_steward"], "skills/docs_steward/"),
    ("context_budget", [sys.executable, "-m", "skills.context_budget.test_context_budget"], "skills/context_budget/"),
    ("nlp_deterministic", [sys.executable, "-m", "skills.nlp_deterministic.test_nlp_deterministic"], "skills/nlp_deterministic/"),
    ("solvers", [sys.executable, "-m", "skills.solvers.test_solvers"], "skills/solvers/"),
    ("cwe_kb", [sys.executable, "-m", "skills.cwe_kb.test_cwe_kb"], "skills/cwe_kb/"),
    ("botte_nn", [sys.executable, "-m", "skills.botte_nn.test_botte_nn"], "skills/botte_nn/"),
    ("features", [sys.executable, "-m", "skills.botte_nn.test_features"], "skills/botte_nn/"),
    ("error_provenance", [sys.executable, "-m", "skills.botte_nn.test_error_classifier_provenance"], "skills/botte_nn/"),
    ("auto_labels", [sys.executable, "-m", "skills.botte_nn.test_auto_labels"], "skills/botte_nn/"),
    ("meta_harness", [sys.executable, "-m", "skills.meta_harness.test_meta_harness"], "skills/meta_harness/"),
    ("reliable_run", [sys.executable, "-m", "skills.meta_harness.test_reliable_run"], "skills/meta_harness/"),
    ("run_contract", [sys.executable, "-m", "skills.run_contract.test_run_contract"], "skills/run_contract/"),
    ("local_harness", [sys.executable, "-m", "skills.local_harness.test_verifier"], "skills/local_harness/"),
    ("harness_executor", [sys.executable, "-m", "skills.local_harness.test_executor"], "skills/local_harness/"),
    ("harness_bench", [sys.executable, "-m", "skills.local_harness.test_bench"], "skills/local_harness/"),
    ("migration_audit", [sys.executable, "-m", "skills.migration_audit.test_migration_audit"], "skills/migration_audit/"),
    ("memory_quarantine", [sys.executable, "-m", "skills.memory_hub.test_quarantine"], "skills/memory_hub/"),
    ("calibration", [sys.executable, "-m", "skills.botte_nn.test_calibration"], "skills/botte_nn/"),
    ("audit_dag", [sys.executable, "-m", "skills.audit_dag.test_audit_dag"], "skills/audit_dag/"),
    ("nn_audit", [sys.executable, "-m", "skills.nn_audit.test_nn_audit"], "skills/nn_audit/"),
    ("hf_provenance", [sys.executable, "-m", "skills.hf_provenance.test_hf_provenance"], "skills/hf_provenance/"),
    ("security_scanner", [sys.executable, "-m", "skills.security_scanner.test_security_scanner"], "skills/security_scanner/"),
    ("context_profiler", [sys.executable, "-m", "skills.context_profiler.test_context_profiler"], "skills/context_profiler/"),
    ("lazy_tools", [sys.executable, "-m", "skills.llm_mcp.test_lazy"], "skills/llm_mcp/"),
    ("events", [sys.executable, "-m", "skills.events.test_events"], "skills/events/"),
    ("quality_compass", [sys.executable, "-m", "skills.trajectory.test_quality"], "skills/trajectory/"),
    ("quality_outcomes", [sys.executable, "-m", "skills.trajectory.test_outcome"], "skills/trajectory/"),
    ("agent_run_manifests", [sys.executable, "-m", "skills.trajectory.test_agent_run"], "skills/trajectory/"),
    ("ci_outcomes", [sys.executable, "-m", "skills.trajectory.test_ci"], "skills/trajectory/"),
    ("task_quality_status", [sys.executable, "-m", "skills.trajectory.test_task_status"], "skills/trajectory/"),
    ("quality_routing_benchmark", [sys.executable, "-m", "skills.trajectory.test_benchmark"], "skills/trajectory/"),
    ("asset_quality", [sys.executable, "-m", "skills.asset_quality.test_asset_quality"], "skills/asset_quality/"),
    ("demo", [sys.executable, "-m", "skills.demo.test_demo"], "skills/demo/"),
    ("bench", [sys.executable, "-m", "skills.bench.test_bench"], "skills/bench/"),
    ("hermes_bridge", [sys.executable, "-m", "skills.hermes_bridge.test_hermes_bridge"], "skills/hermes_bridge/"),
    ("statusline", [sys.executable, "-m", "skills.statusline.test_statusline"], "skills/statusline/"),
]

_RESULT_RE = re.compile(r"(\d+)\s+passed,\s+(\d+)\s+failed")
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
TEST_SUMMARY_PATH = REPO / ".botte-cache" / "test-summary.json"


def _git_changed_files(repo: Path) -> list[str]:
    """Return list of changed files relative to repo root (git diff --name-only)."""
    try:
        proc = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=repo, capture_output=True, text=True, timeout=10,
        )
        if proc.returncode == 0:
            return [l.strip() for l in proc.stdout.splitlines() if l.strip()]
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
        pass
    return []


def _suites_for_changes(changed: list[str]) -> set[int]:
    """Return indices of suites affected by the changed files.

    A changed file matches a suite if its path starts with the suite's module_prefix.
    The e2e suite (index 0) always runs — it tests cross-cutting concerns.
    Scripts/ changes also trigger e2e.
    """
    affected = {0}  # e2e always runs
    for f in changed:
        for idx, (label, cmd, prefix) in enumerate(SUITES):
            if not prefix:  # skip e2e (already handled)
                continue
            if f.startswith(prefix):
                affected.add(idx)
        # scripts/ changes may affect multiple suites
        if f.startswith("scripts/"):
            affected.add(0)  # e2e covers script-level behavior
    return affected


def _git_sha(repo: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=10,
        )
        if proc.returncode != 0:
            return None
        return proc.stdout.strip() or None
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
        return None


def _write_test_summary(*, passed: int, failed: int, suites: int,
                        partial: bool) -> None:
    """Persist the latest observed test result for local/public dashboards."""
    write_json(TEST_SUMMARY_PATH, {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": _git_sha(REPO),
        "passed": passed,
        "failed": failed,
        "suite_count": suites,
        "partial": partial,
        "status": "passed" if failed == 0 else "failed",
    })


def main() -> int:
    p = argparse.ArgumentParser(description="Run Botte Secrète test suites")
    p.add_argument("--changed", action="store_true",
                   help="Only run suites for files changed since last commit")
    p.add_argument("-q", "--quiet", action="store_true",
                   help="Compact output: one line per suite, full detail only on failure")
    args = p.parse_args()

    for s in (sys.stdout, sys.stderr):
        rc = getattr(s, "reconfigure", None)
        if rc:
            try:
                rc(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass

    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
           "PYTHONPATH": str(REPO)}

    # Determine which suites to run
    if args.changed:
        changed = _git_changed_files(REPO)
        if not changed:
            print("Botte Secrète — no changed files, nothing to test")
            return 0
        affected = _suites_for_changes(changed)
        active = [(label, cmd) for i, (label, cmd, _) in enumerate(SUITES) if i in affected]
        if args.quiet:
            print(f"Botte Secrète — {len(active)} suite(s) for {len(changed)} changed file(s)\n")
        else:
            print(f"Botte Secrète — {len(active)} suite(s) for {len(changed)} changed file(s)")
            for f in changed[:10]:
                print(f"  M {f}")
            if len(changed) > 10:
                print(f"  ... and {len(changed) - 10} more")
            print()
    else:
        active = [(label, cmd) for label, cmd, _ in SUITES]
        if not args.quiet:
            print("Botte Secrète — test suites\n")

    total_pass = total_fail = 0
    rows = []
    for label, cmd in active:
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
        row = f"  [{mark}] {label:<18} {p} passed, {f} failed"
        rows.append((row, f, proc, label))

    # Output
    if args.quiet:
        # Only show failures inline; successes are summarized
        failed_rows = [(r, f, proc, label) for r, f, proc, label in rows if f > 0]
        ok_count = len(rows) - len(failed_rows)
        if ok_count:
            print(f"  [OK ] {ok_count} suite(s) passed")
        for row, f, proc, label in failed_rows:
            print(row)
            if proc.stderr:
                print(f"       stderr: {proc.stderr.strip()[:200]}")
            if proc.stdout and f > 0:
                # Show last 3 lines of output for context
                out_lines = proc.stdout.strip().splitlines()
                for l in out_lines[-3:]:
                    print(f"       {l.strip()[:120]}")
        if not failed_rows:
            print(f"\n  ✅ All {ok_count} suites passed")
    else:
        for row, _, _, _ in rows:
            print(row)

    print(f"\nTOTAL: {total_pass} passed, {total_fail} failed")
    try:
        _write_test_summary(
            passed=total_pass,
            failed=total_fail,
            suites=len(rows),
            partial=args.changed,
        )
    except OSError as exc:
        print(f"warning: could not write dashboard test summary: {exc}", file=sys.stderr)
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
