"""CLI for nlp_deterministic — classify / extract entities / keywords (0 tokens).

    python -m skills.nlp_deterministic.cli classify "<text>" label=kw1,kw2 label2=kw3
    python -m skills.nlp_deterministic.cli entities "<text>"
    python -m skills.nlp_deterministic.cli keywords "<text>" [--top 8]
"""

from __future__ import annotations

import argparse
import json
import sys

from skills.console_utf8 import force_utf8
from skills.nlp_deterministic import classify, extract_entities, keywords


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="nlp_deterministic", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("classify", help="intent classification (label=kw1,kw2 …)")
    c.add_argument("text")
    c.add_argument("intents", nargs="+", help="label=comma,separated,keywords")
    c.add_argument("--json", action="store_true")

    e = sub.add_parser("entities", help="extract urls/emails/ips/paths/env/flags/numbers")
    e.add_argument("text")

    k = sub.add_parser("keywords", help="stopword-filtered keyword frequency")
    k.add_argument("text")
    k.add_argument("--top", type=int, default=8)

    args = p.parse_args(argv)

    if args.cmd == "classify":
        intents = {}
        for spec in args.intents:
            if "=" not in spec:
                print(f"ERROR: bad intent spec '{spec}' (use label=kw1,kw2)", file=sys.stderr)
                return 1
            label, kws = spec.split("=", 1)
            intents[label] = [w.strip() for w in kws.split(",") if w.strip()]
        r = classify(args.text, intents)
        if args.json:
            print(json.dumps(r, ensure_ascii=False, indent=2)); return 0
        print(f"🏷️  {r['label']}  (score {r['score']})")
        for lbl, sc in sorted(r["scores"].items(), key=lambda x: -x[1]):
            print(f"   {sc:.3f}  {lbl}")
        return 0

    if args.cmd == "entities":
        print(json.dumps(extract_entities(args.text), ensure_ascii=False, indent=2))
        return 0

    print(json.dumps(keywords(args.text, top_k=args.top), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
