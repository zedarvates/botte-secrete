"""/checkup — the canonical, already-optimal project checkup.

So you never have to hand-write a good checkup prompt: one command runs the
standard sequence in the right order and prints a single verdict.

    python -m skills.checkup.cli [<project>] [--json]

Sequence (cheap → deeper, all local / 0 cloud tokens):
    1. policy        ensure .botte/policy.md exists (the shared rules)
    2. directives    CLAUDE.md/AGENTS.md health + stale refs
    3. metrics       LOC per component + always-on cost + savings framing
    4. infra         hardware/software/MCP cluster tips
    5. duplication   stdlib AST duplicate-function scan
    6. drift         is the MCP wired? are directives stale/oversized?
Then points at the deep code audit (secrets/dead-code) for when you want it.
"""

from __future__ import annotations

import argparse
import json
import sys
from skills.console_utf8 import force_utf8
from pathlib import Path



def run(project: Path) -> dict:
    project = Path(project).resolve()
    out: dict = {"project": str(project), "drift": []}

    # 1. policy present?
    from skills.preflight import policy
    out["policy_committed"] = policy.policy_path(project).exists()
    if not out["policy_committed"]:
        out["drift"].append("No .botte/policy.md — run the deployer to commit shared rules.")

    # 2-5. reuse the auto audit (directives + infra + duplication) and metrics.
    from skills.infra_advisor import auto_audit
    aa = auto_audit(str(project))
    out["headline"] = aa["headline"]
    out["directives"] = aa.get("directives", {})
    out["infra_tips"] = aa.get("infra_tips", [])
    out["duplication"] = aa.get("duplication", {})
    out["diagram"] = aa.get("diagram", "")

    from skills.metrics import collect
    m = collect(project)
    out["loc_total"] = m.loc_total
    out["by_component"] = m.by_component
    out["cost"] = m.cost

    # 6. security — taint / data-flow scan (0 cloud tokens, symbolic)
    out["security"] = _security_summary(project)

    # 7. malicious-pattern scan — dangerous/obfuscated code (0 cloud tokens)
    out["malicious"] = _malicious_summary(project)

    # 8. micro-NN grounding audit (only if the project ships botte_nn)
    out["nn"] = _nn_summary(project)

    # 9. drift checks
    d = out["directives"]
    if isinstance(d, dict):
        if d.get("score", 100) < 90:
            out["drift"].append(f"Directives health {d.get('score')}/100 — stale/oversized; fix CLAUDE.md/AGENTS.md.")
    if any("Wire the MCP" in t.get("title", "") for t in out["infra_tips"]):
        out["drift"].append("MCP not wired here — run `python -m skills.bootstrap.cli .`")
    if m.always_on_tokens > 2000:
        out["drift"].append(f"CLAUDE.md ~{m.always_on_tokens} tok (>2000) — trims save tokens every turn.")
    sec = out["security"]
    if sec.get("high"):
        out["drift"].append(
            f"{sec['high']} security finding(s) (taint/data-flow) — "
            "run `python -m skills.fallow_like.cli taint .`")
    mal = out["malicious"]
    if mal.get("suspicious"):
        out["drift"].append(
            f"{mal['suspicious']} suspicious code pattern(s) "
            "(obfuscation/exfiltration) — run `python -m skills.security_scanner.cli scan .`")
    nn = out["nn"]
    if nn.get("at_risk"):
        out["drift"].append(
            f"{nn['at_risk']} micro-NN(s) synthetic AND wired (drive behaviour "
            "on invented rules) — run `python -m skills.nn_audit.cli`")

    out["deep_audit_hint"] = ("For secrets/dead-code: PYTHONPATH=. python "
                              "skills/mousquetaires/scripts/porthos_audit.py <project> <out>")
    return out


def _security_summary(project: Path) -> dict:
    """Run the taint/data-flow analyzer and summarise it for the checkup."""
    try:
        from skills.fallow_like.config import FallowConfig
        from skills.fallow_like.cli import run_analysis
    except ImportError:
        return {"count": 0, "high": 0, "by_cwe": {}, "top": [], "available": False}
    cfg = FallowConfig(
        project_root=project,
        enable_dead_code=False, enable_duplication=False, enable_complexity=False,
        enable_boundaries=False, enable_feature_flags=False, enable_secrets=False,
        enable_hot_paths=False, enable_blast_radius=False,
    )
    findings = run_analysis(cfg).taint
    by_cwe: dict = {}
    for f in findings:
        by_cwe[f.cwe] = by_cwe.get(f.cwe, 0) + 1
    high = sum(1 for f in findings if f.severity in ("critical", "error"))
    top = [{"file": f.file, "line": f.line, "cwe": f.cwe, "message": f.message,
            "confidence": f.confidence}
           for f in sorted(findings, key=lambda x: -x.confidence)[:5]]
    return {"count": len(findings), "high": high, "by_cwe": by_cwe,
            "top": top, "available": True}


# Genuinely-suspicious patterns (obfuscation / exfiltration / runtime install /
# remote exec) — these rarely appear in legit first-party code, unlike the broad
# eval/exec/subprocess/os_system the scanner also flags. Only these fire drift.
_MALICIOUS_HIGH_SIGNAL = {
    "exec_from_string", "pip_install_from_code", "requests_to_ip",
    "send_environ", "xor_obfuscation", "bytes_decode_obfuscation",
}


_MALICIOUS_CODE_EXTS = {".py", ".rs", ".sh", ".bash", ".js", ".ts"}


def _suspect_excluded(path: str) -> bool:
    """Exclude contexts where high-signal patterns are expected/benign:
    test fixtures, the scanner's own pattern catalog, and declarative config
    (e.g. `pip install` in a CI .yml is not runtime code execution)."""
    p = path.replace("\\", "/").lower()
    name = p.rsplit("/", 1)[-1]
    if name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py":
        return True
    if "/security_scanner/" in p:  # the scanner's own pattern definitions
        return True
    return Path(name).suffix not in _MALICIOUS_CODE_EXTS


def _malicious_summary(project: Path) -> dict:
    """Scan the project for dangerous/obfuscated code patterns (0 cloud tokens).

    Reports the full scan, but only flags the high-signal subset (obfuscation /
    exfiltration / runtime install / remote exec, outside test fixtures) as
    *suspicious* — that subset is what drives drift, to avoid drowning in the
    scanner's high-recall eval/exec/subprocess matches on legit code.
    """
    try:
        from skills.security_scanner import scan_dir, scan_report
    except ImportError:
        return {"count": 0, "suspicious": 0, "by_severity": {}, "top": [], "available": False}
    # fail_on='info' returns *all* findings (every severity is at-least-as-severe as info).
    findings = scan_dir(str(project), fail_on="info")
    rep = scan_report(findings)
    suspicious = [f for f in findings
                  if f.pattern in _MALICIOUS_HIGH_SIGNAL and not _suspect_excluded(f.file)]
    top = [{"file": f.file, "line": f.line, "pattern": f.pattern,
            "severity": f.severity, "snippet": (f.snippet or "")[:80]}
           for f in suspicious[:5]]
    return {"count": rep.count, "suspicious": len(suspicious),
            "by_severity": rep.by_severity, "top": top, "available": True}


def _nn_summary(project: Path) -> dict:
    """Audit micro-NN grounding IF the project ships skills/botte_nn (0 tokens)."""
    botte_nn = Path(project) / "skills" / "botte_nn"
    if not (botte_nn / "models").exists():
        return {"available": False}
    try:
        from skills.nn_audit import audit_models
    except ImportError:
        return {"available": False}
    r = audit_models(botte_nn, scan_root=Path(project) / "skills")
    s = r.get("summary", {})
    at_risk = [m["model"] for m in r.get("models", []) if m.get("risk")]
    orphan = [m["model"] for m in r.get("models", [])
              if not m.get("wired") and m.get("data_source") == "synthetic"]
    return {"available": True, "total": s.get("total", 0),
            "grounded": s.get("grounded", 0), "at_risk": len(at_risk),
            "at_risk_models": at_risk, "orphan_models": orphan,
            "grounded_pct": s.get("grounded_pct", 0)}


def _machine_summary(fresh: bool = False) -> dict:
    """Scan the machine for local-LLM capability (0 tokens, no network by default)."""
    try:
        from skills.llm_backends.audit import audit
    except ImportError:
        return {"available": False}
    try:
        a = audit(fresh=fresh)
    except Exception as e:
        return {"available": False, "error": str(e)}
    return {"available": True, "uses_local_models": a["uses_local_models"],
            "chat_backends": a["chat_backends"],
            "recommended_model": a["recommended_model"], "next_steps": a["next_steps"]}


def _rank_actions(result: dict, project: Path) -> list[dict]:
    """Top opportunities, ranked — fixes by cost-to-apply (tokens), drift items
    by risk (no token estimate, but they're free to fix and cheap to skip). Fixes
    surface first since they carry a concrete number; the roadmap's "reuse the
    cost framing of fix/metrics" instead of inventing a new savings model."""
    actions: list[dict] = []
    try:
        from skills.fix import find_fixes
        f = find_fixes(project)
        for kind, cost in sorted(f.get("cost_by_kind", {}).items(),
                                  key=lambda kv: -(kv[1].get("tokens_in", 0)
                                                    + kv[1].get("tokens_out", 0))):
            actions.append({
                "action": f"Fix {cost['count']} {kind} issue(s)",
                "est_tokens": cost.get("tokens_in", 0) + cost.get("tokens_out", 0),
                "est_usd": cost.get("usd", 0.0),
                "how": "python -m skills.fix.cli . --save md",
            })
    except Exception:
        pass
    for item in result.get("drift", []):
        actions.append({"action": item, "est_tokens": None, "est_usd": None, "how": ""})
    return actions[:3]


def _verdict(result: dict) -> str:
    drift_n = len(result.get("drift", []))
    machine = result.get("machine", {}) or {}
    if drift_n == 0 and (not machine.get("available") or machine.get("uses_local_models")):
        return "✅ sain — rien à corriger, routing local actif."
    if drift_n == 0:
        return ("⚠️ sain côté code, mais aucun backend local détecté — "
                "chaque tâche part au cloud. Voir 'machine' ci-dessous.")
    top = _rank_actions(result, Path(result["project"]))
    tok = sum(a["est_tokens"] or 0 for a in top)
    tok_note = f", ~{tok:,} tokens d'opportunités identifiées" if tok else ""
    return f"⚠️ {drift_n} optimisation(s) disponible(s){tok_note}."


def doctor(project: Path, *, machine_fresh: bool = False) -> dict:
    """The full checkup, plus a machine scan and a ranked action list — one
    verb that assembles checkup + llm_backends + fix into a single verdict."""
    r = run(project)
    r["machine"] = _machine_summary(fresh=machine_fresh)
    r["top_actions"] = _rank_actions(r, project)
    r["verdict"] = _verdict(r)
    return r


# Stable marker so a CI bot can find & update its own comment instead of spamming.
PR_COMMENT_MARKER = "<!-- botte-checkup -->"


def format_pr_comment(result: dict, *, repo: str | None = None,
                      sha: str | None = None) -> str:
    """Render a checkup result as a Markdown PR comment. Pure — no I/O.

    Verdict-first: a clear pass/drift line, the headline + key numbers, and the
    actionable drift list. Carries a stable marker so the workflow can edit its
    previous comment in place.
    """
    drift = result.get("drift", []) or []
    cost = result.get("cost", {}) or {}
    verdict = "✅ **No drift** — project is in good shape." if not drift else (
        f"⚠️ **{len(drift)} drift item{'s' if len(drift) != 1 else ''} to fix**")

    lines = [PR_COMMENT_MARKER, "## 🧦 Botte Secrète — checkup", "", verdict, ""]
    headline = result.get("headline")
    if headline:
        lines.append(f"> {headline}")
        lines.append("")

    loc = result.get("loc_total")
    policy_ok = result.get("policy_committed")
    facts = []
    if loc is not None:
        facts.append(f"**{loc:,}** LOC")
    facts.append(f"policy {'✓ committed' if policy_ok else '✗ not committed'}")
    if "analysis_llm_tokens" in cost:
        facts.append(f"analysis cost **{cost['analysis_llm_tokens']} LLM tokens**")
    if "always_on_tokens_per_session" in cost:
        facts.append(f"always-on **{cost['always_on_tokens_per_session']:,} tok/session**")
    lines.append(" · ".join(facts))
    lines.append("")

    if drift:
        lines.append("### Drift to fix")
        for x in drift:
            lines.append(f"- {x}")
        lines.append("")

    sec = result.get("security") or {}
    if sec.get("count"):
        cwes = ", ".join(f"{k}×{v}" for k, v in sorted(sec.get("by_cwe", {}).items()))
        lines.append(f"### 🛡️ Security — {sec['count']} taint candidate(s) "
                     f"({sec.get('high', 0)} high) · {cwes}")
        for t in sec.get("top", []):
            lines.append(f"- `{t['file']}:{t['line']}` [{t['cwe']}] {t['message']} "
                         f"(conf {t['confidence']})")
        lines.append("")
    elif sec.get("available"):
        lines.append("### 🛡️ Security — no taint/data-flow candidates")
        lines.append("")

    mal = result.get("malicious") or {}
    if mal.get("suspicious"):
        bys = mal.get("by_severity", {})
        sevs = " ".join(f"{k}×{v}" for k, v in bys.items() if v)
        lines.append(f"### 🦠 Malicious-pattern scan — {mal['suspicious']} suspicious "
                     f"(obfuscation/exfiltration) of {mal['count']} total · {sevs}")
        for t in mal.get("top", []):
            lines.append(f"- `{t['file']}:{t['line']}` [{t['severity']}] {t['pattern']}"
                         + (f" — `{t['snippet']}`" if t.get('snippet') else ""))
        lines.append("")
    elif mal.get("available"):
        lines.append(f"### 🦠 Malicious-pattern scan — no suspicious patterns "
                     f"({mal.get('count', 0)} powerful-primitive matches reviewed)")
        lines.append("")

    nn = result.get("nn") or {}
    if nn.get("available"):
        if nn.get("at_risk"):
            lines.append(f"### 🧠 Micro-NN grounding — {nn['grounded']}/{nn['total']} grounded, "
                         f"{nn['at_risk']} synthetic+wired: {', '.join(nn['at_risk_models'])}")
        else:
            lines.append(f"### 🧠 Micro-NN grounding — {nn['grounded']}/{nn['total']} grounded, "
                         "none synthetic-and-wired")
        lines.append("")

    footer = "_local-first checkup · 0 cloud tokens_"
    if repo and sha:
        footer += f" · [`{sha[:7]}`](https://github.com/{repo}/commit/{sha})"
    lines.append(footer)
    return "\n".join(lines)


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="checkup", description=__doc__)
    p.add_argument("project", nargs="?", default=".")
    p.add_argument("--json", action="store_true")
    p.add_argument("--pr-comment", action="store_true",
                   help="print a Markdown PR comment (for the GitHub Action)")
    p.add_argument("--save", nargs="?", const="both", choices=["md", "html", "both"],
                   help="save a timestamped report under <project>/.botte/reports/")
    p.add_argument("--doctor", action="store_true",
                   help="also scan the machine (local-LLM capability) and rank "
                        "top opportunities by estimated token cost")
    p.add_argument("--fresh", action="store_true",
                   help="with --doctor, re-scan for local backends instead of "
                        "reading the cached registry")
    args = p.parse_args(argv)

    r = (doctor(Path(args.project), machine_fresh=args.fresh) if args.doctor
         else run(Path(args.project)))
    if args.doctor and not args.json and not args.pr_comment:
        print(f"🩺 {r['verdict']}")
        m = r.get("machine", {})
        if m.get("available"):
            local = "✓ local backend(s): " + ", ".join(m["chat_backends"]) \
                if m.get("uses_local_models") else "✗ no local backend detected"
            print(f"   machine: {local}")
            if not m.get("uses_local_models"):
                for step in m.get("next_steps", [])[:3]:
                    print(f"     {step}")
        if r.get("top_actions"):
            print("\n   🎯 top opportunities:")
            for a in r["top_actions"]:
                cost = f" (~{a['est_tokens']:,} tok · ${a['est_usd']:.4f})" \
                    if a.get("est_tokens") else ""
                print(f"     • {a['action']}{cost}")
                if a.get("how"):
                    print(f"       → {a['how']}")
        print()
    if args.pr_comment:
        import os
        print(format_pr_comment(r, repo=os.environ.get("GITHUB_REPOSITORY"),
                                sha=os.environ.get("GITHUB_SHA")))
        return 0
    if args.save:
        from skills.report import save
        paths = save("checkup", r, fmt=args.save,
                     out_dir=Path(r["project"]) / ".botte" / "reports",
                     title=f"Checkup — {r['project']}")
        r["saved_report"] = paths
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0

    print(f"🩺 Checkup — {r['project']}")
    print(f"   {r['headline']}  ·  {r['loc_total']:,} LOC  ·  "
          f"policy {'✓' if r['policy_committed'] else '✗ (not committed)'}")
    print(f"\n   💰 analysis cost: {r['cost']['analysis_llm_tokens']} LLM tokens · "
          f"always-on: {r['cost']['always_on_tokens_per_session']:,} tok/session")
    sec = r.get("security") or {}
    if sec.get("count"):
        cwes = ", ".join(f"{k}×{v}" for k, v in sorted(sec.get("by_cwe", {}).items()))
        print(f"\n   🛡️  Security: {sec['count']} taint candidate(s) "
              f"({sec.get('high', 0)} high) · {cwes}")
    elif sec.get("available"):
        print("\n   🛡️  Security: no taint/data-flow candidates")
    mal = r.get("malicious") or {}
    if mal.get("suspicious"):
        print(f"\n   🦠 Malicious patterns: {mal['suspicious']} suspicious "
              f"(obfuscation/exfiltration) of {mal['count']} total")
    elif mal.get("available"):
        print(f"\n   🦠 Malicious patterns: clean ({mal.get('count', 0)} reviewed)")
    nn = r.get("nn") or {}
    if nn.get("available"):
        extra = (f" · at-risk: {', '.join(nn['at_risk_models'])}"
                 if nn.get("at_risk") else "")
        print(f"\n   🧠 Micro-NN: {nn['grounded']}/{nn['total']} grounded{extra}")
    if r["drift"]:
        print("\n   ⚠️  Drift to fix:")
        for x in r["drift"]:
            print(f"     • {x}")
    else:
        print("\n   ✅ No drift.")
    print(f"\n   🔬 {r['deep_audit_hint']}")
    if r.get("saved_report"):
        print("\n   💾 Saved: " + " · ".join(r["saved_report"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
