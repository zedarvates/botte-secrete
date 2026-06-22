"""CLI for docs_steward — scoped documentation map.

    python -m skills.docs_steward.cli map   <project> [--json]
    python -m skills.docs_steward.cli index <project> [--write] [--component NAME]
"""

from __future__ import annotations

import argparse
import json
import sys

from skills.console_utf8 import force_utf8
from skills.docs_steward import build_map, write_indexes


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

    args = p.parse_args(argv)

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
