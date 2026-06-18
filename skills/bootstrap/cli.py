"""CLI for the project deployer.

    python -m skills.bootstrap.cli <project> [--create-agents-md] [--scan-subnet] [--json]

Installs Botte Secrète into <project>: MCP tools, directives audit, .botte config.
"""

from __future__ import annotations

import argparse
import json
import sys

from skills.bootstrap.setup import setup


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
    p = argparse.ArgumentParser(prog="botte-setup", description=__doc__)
    p.add_argument("project", help="target project directory")
    p.add_argument("--create-agents-md", action="store_true",
                   help="scaffold AGENTS.md if the project has no agent instructions")
    p.add_argument("--scan-subnet", action="store_true",
                   help="also sweep the local /24 for LLM backends")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    rep = setup(args.project, create_agents_md=args.create_agents_md,
                scan_subnet=args.scan_subnet)

    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        return 0

    print(f"🧦 Botte Secrète deployed → {rep['project']}")
    print(f"   MCP: {rep['mcp']['action']} '{rep['mcp']['path']}' "
          f"(botte-llm; kept: {rep['mcp']['other_servers'] or 'none'})")
    print(f"   Local backends: {rep['local_backends'] or 'none detected'}")
    print(f"   Cloud keys: {rep['cloud_keys_present'] or 'none'}")
    d = rep["directives"]
    if d.get("available"):
        extra = f", created {d['created']}" if d.get("created") else ""
        print(f"   Directives: score {d['score']}/100, "
              f"{'has instructions' if d['has_instructions'] else 'NO instructions'}{extra}")
    print(f"   Skill catalog (free local search): {rep['skill_catalog_size']} skills")
    print(f"   Config + report: {rep['project']}/.botte/")
    print("\n   Next steps:")
    for s in rep["next_steps"]:
        print(f"     • {s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
