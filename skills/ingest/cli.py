"""CLI for ingest — local scraping + Qdrant ingestion.

    python -m skills.ingest.cli scrape <url> [--structure] [--json]
    python -m skills.ingest.cli ingest <url|file> [--collection C] [--qdrant H:P]
    python -m skills.ingest.cli search "<query>" [--collection C] [--qdrant H:P]
"""

from __future__ import annotations

import argparse
import json
import sys
from skills.console_utf8 import force_utf8

from skills.ingest import scrape, ingest, search



def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="ingest", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scrape", help="fetch + extract a page locally")
    s.add_argument("url"); s.add_argument("--structure", action="store_true")
    s.add_argument("--json", action="store_true")

    s = sub.add_parser("ingest", help="scrape/ingest a source into Qdrant")
    s.add_argument("source"); s.add_argument("--collection", default="botte_ingest")
    s.add_argument("--qdrant", default="192.168.1.47:6333")
    s.add_argument("--file", action="store_true", help="source is a file/text, not a URL")

    s = sub.add_parser("search", help="recall from a Qdrant collection")
    s.add_argument("query"); s.add_argument("--collection", default="botte_ingest")
    s.add_argument("--qdrant", default="192.168.1.47:6333")

    args = p.parse_args(argv)

    if args.cmd == "scrape":
        sc = scrape(args.url, structure=args.structure)
        if args.json:
            print(json.dumps(sc.to_dict(), ensure_ascii=False, indent=2)); return 0
        print(f"📄 {sc.title or '(no title)'}  ({sc.chars} chars)  {sc.url}")
        if sc.structured:
            print(json.dumps(sc.structured, ensure_ascii=False, indent=2))
        else:
            print(sc.text[:800] + (" …" if len(sc.text) > 800 else ""))
        return 0

    if args.cmd == "ingest":
        r = ingest(args.source, collection=args.collection, qdrant=args.qdrant,
                   is_url=not args.file)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0 if r.get("stored") else 1

    r = search(args.query, collection=args.collection, qdrant=args.qdrant)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
