"""CLI for the read-only RSI graph observer."""

import argparse
import json
from .observer import build_graph

def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only RSI graph observer")
    sub = parser.add_subparsers(dest="command", required=True)
    observe = sub.add_parser("observe", help="reconstruct graph from existing events")
    observe.add_argument("project", nargs="?", default=".")
    observe.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    graph = build_graph(args.project)
    if args.json:
        print(json.dumps(graph, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("RSI graph: %d events, %d nodes, %d edges" % (graph["event_count"], len(graph["nodes"]), len(graph["edges"])))
        for note in graph["limitations"]:
            print("- " + note)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
