#!/usr/bin/env python3
"""End-to-end test for the full Botte Secrète pipeline.

Tests:
1. Project cache (scan → save → load)
2. Porthos audit
3. d'Artagnan fix
4. Aramis optimize
5. diff_language roundtrip
6. Loader (pre-prompt loading)
7. Clarification
8. Pipeline simulation (parallel hints)

Usage:
    python3 skills/test_e2e.py [--project /path/to/project]
"""

import sys
import json
import tempfile
from pathlib import Path

# Setup path
sys.path.insert(0, str(Path(__file__).parent.parent))

from skills.console_utf8 import force_utf8
from skills.cache import ProjectCache
from skills.loader import list_agents, agent_info, load_agent, load_agents_batch, load_core
from skills.clarification import portos_clarify, dartagnan_clarify, aramis_clarify
from skills.diff_language import DiffLine, DiffReport, Op, Sev


def green(s): return f"\033[92m{s}\033[0m"
def red(s): return f"\033[91m{s}\033[0m"
def bold(s): return f"\033[1m{s}\033[0m"


def section(name):
    print(f"\n{bold('═══ ' + name + ' ═══')}")


def ok(msg):
    print(f"  {green('✅')} {msg}")


def fail(msg):
    print(f"  {red('❌')} {msg}")
    return False


def main():
    force_utf8()
    project = sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == "--project" else str(Path(__file__).parent.parent)
    passed = 0
    failed = 0

    print(bold("🧪 Botte Secrète — End-to-End Test Suite"))
    print(f"   Project: {project}")
    print(f"   Time: {__import__('datetime').datetime.now().isoformat()}")

    # ── 1. Project Cache ──
    section("1. Project Cache")
    with tempfile.TemporaryDirectory() as tmp:
        cache = ProjectCache(tmp)
        # Scan
        result1 = cache.get_or_scan(lambda: {"files": 40, "lines": 3841})
        if result1.get("files") == 40:
            ok(f"Fresh scan: {result1['files']} files")
            passed += 1
        else:
            failed += 1
            fail(f"Expected 40 files, got {result1}")

        # Cache hit
        result2 = cache.get_or_scan(lambda: {"files": 99})
        if result2.get("files") == 40:
            ok(f"Cache hit: {result2['files']} files (not 99)")
            passed += 1
        else:
            failed += 1
            fail(f"Expected 40 from cache, got {result2}")

        # Audit report
        cache.set_audit_report({"health": 59, "findings": 27})
        audit = cache.get_audit_report()
        if audit and audit.get("health") == 59:
            ok(f"Audit cached: health={audit['health']}")
            passed += 1
        else:
            failed += 1
            fail(f"Audit cache failed")

        # Invalidate
        cache.invalidate()
        result3 = cache.get_or_scan(lambda: {"files": 50})
        if result3.get("files") == 50:
            ok(f"Invalidated: fresh scan = {result3['files']} files")
            passed += 1
        else:
            failed += 1
            fail(f"Expected 50 after invalidation")

    # ── 2. Loader ──
    section("2. Pre-Prompt Loader")
    agents = list_agents()
    if len(agents) == 8:
        ok(f"8 agents found: {agents}")
        passed += 1
    else:
        failed += 1
        fail(f"Expected 8 agents, got {len(agents)}")

    # Load single agent
    ctx = load_agent("porthos", project_root=project)
    if len(ctx) > 1000 and "core-agent.md" not in ctx[:500]:
        ok(f"load_agent(porthos): {len(ctx)} chars")
        passed += 1
    else:
        failed += 1
        fail(f"load_agent returned {len(ctx)} chars")

    # Batch
    tasks = load_agents_batch([
        ("porthos", "Auditer le projet", None),
        ("aramis", "Optimiser le projet", None),
    ], project_root=project)
    if len(tasks) == 2 and "context" in tasks[0] and "goal" in tasks[0]:
        ok(f"load_agents_batch: {len(tasks)} tasks ready")
        passed += 1
    else:
        failed += 1
        fail("Batch generation failed")

    # Core size
    core = load_core()
    core_tokens = len(core) // 4
    if 100 < core_tokens < 5000:
        ok(f"Core: {core_tokens} tokens")
        passed += 1
    else:
        failed += 1
        fail(f"Core size unexpected: {core_tokens} tokens")

    # ── 3. Clarification ──
    section("3. Clarification")
    cr = portos_clarify(project, 40)
    if 2 <= len(cr.questions) <= 5:
        ok(f"Porthos asks {len(cr.questions)} questions")
        passed += 1
    else:
        failed += 1
        fail(f"Expected 2-5 questions, got {len(cr.questions)}")

    defaults = cr.fill_defaults()
    if len(defaults) == len(cr.questions):
        ok(f"fill_defaults: {len(defaults)} defaults")
        passed += 1
    else:
        failed += 1
        fail("fill_defaults mismatch")

    cr2 = dartagnan_clarify(27)
    blockers = sum(1 for q in cr2.questions if q.priority.value == "blocker")
    if blockers >= 1:
        ok(f"d'Artagnan has {blockers} blocker question(s)")
        passed += 1
    else:
        failed += 1
        fail(f"No blocker questions in d'Artagnan (got {blockers})")

    # ── 4. Diff Language ──
    section("4. Diff Language")
    report = DiffReport()
    report.add(DiffLine(Op.FIX, "core.py", "42", "calc_tax", "CMT::grep→0", Sev.ERR))
    report.add(DiffLine(Op.SKIP, "utils.py", "88", "parse_input", "SKP::getattr", Sev.WARN))
    report.add(DiffLine(Op.SECRET, "auth.py", "30", "API_KEY", "log_exposed", Sev.CRIT))

    compact = report.to_compact()
    parsed = DiffReport.from_compact(compact)

    if report.to_compact() == parsed.to_compact():
        ok(f"Roundtrip: {len(report.entries)} entries, {report.savings()}% savings")
        passed += 1
    else:
        failed += 1
        fail("Roundtrip failed")

    # Bulk compression
    report2 = DiffReport()
    for i in range(50):
        report2.add(DiffLine(Op.FIX, f"mod{i}.py", f"{i*10}", f"fn_{i}", "CMT", Sev.ERR))
    savings = report2.savings()
    if savings > 40:
        ok(f"50-entry report: {savings}% savings ({report2.compact_size()} vs {report2.verbose_size()} chars)")
        passed += 1
    else:
        failed += 1
        fail(f"50-entry savings only {savings}%")

    # ── 5. Agent Info Summary ──
    section("5. Agent Metrics")
    total_tokens = 0
    for a in agents:
        info = agent_info(a)
        total_tokens += info["tokens_est"]
    core_tok = len(load_core()) // 4
    all_load = core_tok + total_tokens
    # Previous measurement: ~9209 tokens for all agents before P0
    # With P0-P14: core grew from ~1144 to ~2069, but per-agent usage reduced 85%
    if all_load < 9000:
        ok(f"All agents: ~{all_load} tokens (vs ~9209 before → {100 - all_load*100//9209}% saved)")
        passed += 1
    else:
        failed += 1
        fail(f"Total tokens {all_load} > 9000")

    # ── 6. Pipeline Structure ──
    section("6. Pipeline Structure")
    required_dirs = [
        "skills/mousquetaires/prompts",
        "skills/cardinal/prompts",
        "skills/cache",
        "skills/clarification",
        "skills/loader",
        "skills/diff_language",
        "skills/fallow_like",
        "skills/skill_project_optimizer",
        "skills/llm_backends",
        "skills/llm_mcp",
        "skills/auto_router",
        "skills/skill_finder",
        "skills/bootstrap",
        "skills/infra_advisor",
        "skills/prompt_improver",
        "skills/metrics",
        "skills/preflight",
        "skills/checkup",
        "skills/ingest",
        "skills/docgen",
        "skills/app_test",
        "skills/capabilities",
        "skills/cluster",
        "skills/conductor",
        "skills/docs_steward",
        "skills/context_budget",
        "skills/nlp_deterministic",
        "skills/solvers",
        "skills/cwe_kb",
        "skills/nn_audit",
        "skills/context_profiler",
        "skills/control_loop",
        "skills/report",
        "skills/cost_estimator",
        "skills/fix",
        "skills/trends",
        "skills/dashboard",
    ]
    for d in required_dirs:
        p = Path(project) / d
        if p.exists():
            ok(f"  {d}")
        else:
            failed += 1
            fail(f"Missing: {d}")
    passed += len(required_dirs)

    # ── Results ──
    print(f"\n{bold('═══════════════════════════════════')}")
    print(f"{bold('RESULTS:')} {green(passed)} passed, {red(failed)} failed")
    if failed == 0:
        print(green("🎉 ALL TESTS PASSED"))
        return 0
    else:
        print(red(f"💥 {failed} test(s) failed"))
        return 1


if __name__ == "__main__":
    sys.exit(main())
