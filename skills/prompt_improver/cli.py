"""CLI for prompt_improver — the /p-amelioration entry point.

    python -m skills.prompt_improver.cli "make my code faster"
    python -m skills.prompt_improver.cli "summarize this PR" --json
    python -m skills.prompt_improver.cli "..." --no-local      # deterministic scaffold only
"""

from __future__ import annotations

import argparse
import json
import sys

from skills.prompt_improver.improver import improve


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
    p = argparse.ArgumentParser(prog="p-amelioration", description=__doc__)
    p.add_argument("prompt", help="the rough prompt to improve")
    p.add_argument("--json", action="store_true", help="emit a JSON prompt object")
    p.add_argument("--no-local", action="store_true", help="skip the local LLM (scaffold only)")
    p.add_argument("--raw", action="store_true", help="print full JSON result")
    args = p.parse_args(argv)

    res = improve(args.prompt, as_json=args.json, use_local=not args.no_local)
    if "error" in res:
        print(f"ERROR: {res['error']}", file=sys.stderr)
        return 1
    if args.raw:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    print(f"# improved via {res['tier']} (cloud tokens: {res['cloud_tokens']})\n")
    print(res["json_prompt"] if args.json and "json_prompt" in res else res["markdown"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
