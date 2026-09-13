"""CLI for completion_proof — policy A11 detector (done without proof).

    python -m skills.completion_proof.cli [<path>] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys

from skills.completion_proof import audit_path
from skills.console_utf8 import force_utf8


def strict_exit_code(result: dict) -> int:
    """Only a consistent verified result can authorize the caller's next step."""
    if (result.get("status") == "verified_on_recorded_tests"
            and result.get("verified") is True and result.get("errors") == []):
        return 0
    if any(error in {"unreadable_file", "root_or_io_error"}
           for error in result.get("errors", [])):
        return 7
    return {"missing_evidence": 3, "test_failed": 5, "announced": 6}.get(
        result.get("status"), 4)


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="completion_proof", description=__doc__)
    p.add_argument("path", nargs="?", default=".",
                   help="report file or directory to audit (default: current dir)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--verify", action="store_true", help="verify a v1 receipt (read-only)")
    p.add_argument("--strict", action="store_true", help="with --verify: exit nonzero unless verified")
    p.add_argument("--evidence-root")
    p.add_argument("--source-root")
    p.add_argument("--receipt-sha256", help="trusted digest obtained outside the report")
    args = p.parse_args(argv)

    verification_args = (args.evidence_root, args.source_root, args.receipt_sha256)
    if args.strict and not args.verify:
        p.error("--strict requires --verify")
    if args.verify:
        if not all(verification_args):
            p.error("--verify requires --evidence-root, --source-root and --receipt-sha256")
        from skills.completion_proof.verify import verify_report
        result = verify_report(args.path, evidence_root=args.evidence_root,
                               source_root=args.source_root,
                               trusted_receipt_sha256=args.receipt_sha256)
        if args.json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(result["status"])
            for error in result["errors"]:
                print(f"  {error}")
        return strict_exit_code(result) if args.strict else 0
    if any(verification_args):
        p.error("evidence arguments require --verify")

    r = audit_path(args.path)
    if "error" in r:
        print(f"ERROR: {r['error']}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(r, ensure_ascii=False))
        return 0

    s = r["summary"]
    print(f"A11 completion-proof audit — {r['target']}")
    print(f"   {r['files_scanned']} files · {s['total']} unproven completions\n")
    for f in r["findings"][:15]:
        print(f"   ⚠ {f['preuve']}")
        print(f"      cout: {f['cout_estime']}")
        print(f"      gain: {f['gain_attendu']}")
        print(f"      risque: {f['risque']}")
        print(f"      refactoring minimal: {f['refactoring_minimal']}\n")
    if s["total"] > 15:
        print(f"   … +{s['total'] - 15} autres (voir --json)")
    return 0  # report-only; never fails the build


if __name__ == "__main__":
    raise SystemExit(main())
