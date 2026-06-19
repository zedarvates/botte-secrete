"""CLI for docgen.

    python -m skills.docgen.cli draft "<topic>" [--kind readme|module|changelog|guide|adr]
    python -m skills.docgen.cli session <transcript.jsonl> [--text]
"""

from __future__ import annotations

import argparse
import json
import sys

from skills.docgen import draft_doc, session_review


def _utf8():
    for s in (sys.stdout, sys.stderr):
        rc = getattr(s, "reconfigure", None)
        if rc:
            try:
                rc(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def main(argv=None) -> int:
    _utf8()
    p = argparse.ArgumentParser(prog="docgen", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("draft", help="local draft → cloud refine of a doc")
    s.add_argument("topic")
    s.add_argument("--kind", default="guide",
                   choices=["readme", "module", "changelog", "guide", "adr"])
    s.add_argument("--context", default="")
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("session", help="local review of a session transcript")
    s.add_argument("source"); s.add_argument("--text", action="store_true",
                                             help="source is raw text, not a file")
    s.add_argument("--json", action="store_true")

    args = p.parse_args(argv)

    if args.cmd == "draft":
        r = draft_doc(args.topic, kind=args.kind, context=args.context)
        if args.json:
            print(json.dumps(r, ensure_ascii=False, indent=2)); return 0
        print(f"# docgen [{r.get('kind')}] refined_by={r.get('refined_by')}\n")
        print(r.get("doc") or r.get("error", ""))
        return 0

    r = session_review(args.source, is_file=not args.text)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if "error" not in r else 1


if __name__ == "__main__":
    raise SystemExit(main())
