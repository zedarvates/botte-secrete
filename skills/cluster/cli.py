"""CLI for the cluster scheduler.

    python -m skills.cluster.cli status [--subnet] [--json]
    python -m skills.cluster.cli pick [--strategy lru|latency]
    python -m skills.cluster.cli delegate <host> "<task>" [--url URL]
"""

from __future__ import annotations

import argparse
import json
import sys

from skills.console_utf8 import force_utf8
from skills.cluster.cluster import status, pick, delegate


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="cluster", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("status", help="cluster overview + recommended target")
    s.add_argument("--subnet", action="store_true"); s.add_argument("--json", action="store_true")

    s = sub.add_parser("pick", help="choose a backend across machines")
    s.add_argument("--strategy", choices=["lru", "latency"], default="lru")

    s = sub.add_parser("delegate", help="hand a task to a machine's agent endpoint")
    s.add_argument("host"); s.add_argument("task"); s.add_argument("--url", default=None)

    args = p.parse_args(argv)

    if args.cmd == "status":
        r = status(scan_subnet=args.subnet)
        if args.json:
            print(json.dumps(r, ensure_ascii=False, indent=2)); return 0
        print(f"🖥️  Cluster — {r['machine_count']} machine(s), "
              f"{len(r['chat_capable'])} chat-capable")
        for m in r["machines"]:
            tag = ", ".join(f"{b['label']}:{b['port']}" for b in m["backends"])
            print(f"   {m['host']:16} {m['min_latency_ms']:>4}ms  [{tag}]")
        lru, fast = r.get("recommended_lru"), r.get("recommended_fastest")
        if lru:
            print(f"\n   → spread work (LRU):  {lru['host']}:{lru['port']} ({lru['model']})")
            print(f"   → fastest (latency):  {fast['host']}:{fast['port']}")
        return 0

    if args.cmd == "pick":
        r = pick(args.strategy)
        print(json.dumps(r, ensure_ascii=False, indent=2) if r else "no chat backend")
        return 0 if r else 1

    r = delegate(args.host, args.task, agent_url=args.url)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r.get("delegated") else 1


if __name__ == "__main__":
    raise SystemExit(main())
