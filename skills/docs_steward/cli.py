"""CLI for docs_steward — scoped documentation map + docs lifecycle.

    python -m skills.docs_steward.cli map     <project> [--json]
    python -m skills.docs_steward.cli index   <project> [--write] [--component NAME]
    python -m skills.docs_steward.cli tasks   <project> [--keep N]      # lifecycle summary
    python -m skills.docs_steward.cli prune   <project> [--write]       # strip finished tasks
    python -m skills.docs_steward.cli reports <project> [--keep N] [--archive]
"""

from __future__ import annotations

import argparse
import json
import sys

from skills.console_utf8 import force_utf8
from skills.docs_steward import (build_map, write_indexes, lifecycle_report,
                                 prune_all, archive_reports)


def _cmd_tasks(args) -> int:
    r = lifecycle_report(args.project, keep=args.keep)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0
    t, rep = r["tasks"], r["reports"]
    print(f"🗂️  Lifecycle — {args.project}")
    print(f"   tasks: {t['open_total']} open · {t['done_total']} done "
          f"(~{t['done_token_waste']} tok of finished items still in-file)")
    if t["fully_done_files"]:
        print(f"   fully-done plans to archive: {', '.join(t['fully_done_files'])}")
    print(f"   reports: {rep['total']} files / {rep['names']} kinds · "
          f"keep {rep['keep']} · {rep['to_archive']} to archive")
    if t["done_total"] or rep["to_archive"]:
        print("\n   → `prune --write` to strip finished tasks · "
              "`reports --archive` to tidy reports")
    return 0


def _cmd_prune(args) -> int:
    results = prune_all(args.project, dry_run=not args.write)
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0
    actionable = [r for r in results if r["action"] != "none"]
    if not actionable:
        print("No finished tasks to prune.")
        return 0
    for r in actionable:
        verb = "✂️  Pruned" if args.write else "👀 Would prune"
        print(f"{verb} {r['path']} — {r['action']} ({r['removed']} done item(s)"
              f" → {r.get('archived_to', '')})")
    if not args.write:
        print("(preview — pass --write to apply; removed items are archived, not lost)")
    return 0


def _cmd_reports(args) -> int:
    moved = archive_reports(args.project, keep=args.keep, dry_run=not args.archive)
    if args.json:
        print(json.dumps(moved, ensure_ascii=False, indent=2))
        return 0
    if not moved:
        print(f"Nothing to archive (≤ {args.keep} per report name).")
        return 0
    verb = "📦 Archived" if args.archive else "👀 Would archive"
    for m in moved:
        print(f"{verb} {m['name']} @ {m['when']} → {m['to']}")
    if not args.archive:
        print("(preview — pass --archive to move them)")
    return 0


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="docs_steward", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("map", help="show the scoped documentation map")
    s.add_argument("project", nargs="?", default=".")
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("index", help="render (or write) a per-component DOCS.md")
    s.add_argument("project", nargs="?", default=".")
    s.add_argument("--write", action="store_true", help="write the files (default: preview)")
    s.add_argument("--component", default=None, help="only this component")
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("tasks", help="lifecycle of plans/TODOs + report hygiene")
    s.add_argument("project", nargs="?", default=".")
    s.add_argument("--keep", type=int, default=5, help="reports to keep per name")
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("prune", help="strip finished tasks (archived, not lost)")
    s.add_argument("project", nargs="?", default=".")
    s.add_argument("--write", action="store_true", help="apply (default: preview)")
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("reports", help="archive older .botte reports, keep N recent")
    s.add_argument("project", nargs="?", default=".")
    s.add_argument("--keep", type=int, default=5)
    s.add_argument("--archive", action="store_true", help="move them (default: preview)")
    s.add_argument("--json", action="store_true")

    args = p.parse_args(argv)

    if args.cmd == "tasks":
        return _cmd_tasks(args)
    if args.cmd == "prune":
        return _cmd_prune(args)
    if args.cmd == "reports":
        return _cmd_reports(args)

    if args.cmd == "map":
        m = build_map(args.project)
        if args.json:
            print(json.dumps(m, ensure_ascii=False, indent=2))
            return 0
        print(f"📚 Docs map — {m['project']}")
        print(f"   global docs: {len(m['global_docs'])} (~{m['global_tokens']} tok) · "
              f"total project docs ~{m['total_doc_tokens']} tok\n")
        if not m["components"]:
            print("   (no components detected — single-component project)")
        for c in m["components"]:
            print(f"   • {c['name']:14} [{c['kind']:9}] {len(c['local_docs'])} local doc(s) "
                  f"· local ~{c['local_tokens']} tok · scoped load ~{c['scoped_tokens']} tok")
        print(f"\n   {m['savings_note']}")
        return 0

    # index
    results = write_indexes(args.project, dry_run=not args.write,
                            only=args.component)
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0
    if not results:
        print("No components to index.")
        return 0
    for r in results:
        verb = "✍️  Wrote" if r["written"] else "👀 Would write"
        print(f"\n{verb} {r['path']}\n{'─' * 60}")
        print(r["content"])
    if not args.write:
        print("(preview — pass --write to create these files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
