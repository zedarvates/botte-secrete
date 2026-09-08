"""Inspect and safely release Botte workspace leases."""

from __future__ import annotations

import argparse
import json
import sys

from skills.console_utf8 import force_utf8
from skills.meta_harness.lease import WorktreeLeaseManager, WorkspaceLeaseError


def main(argv=None) -> int:
    force_utf8()
    parser = argparse.ArgumentParser(prog="botte lease", description=__doc__)
    parser.add_argument("--project", default=".")
    parser.add_argument("--workspace-root")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    inspect = sub.add_parser("inspect")
    inspect.add_argument("lease_id")
    release = sub.add_parser("release")
    release.add_argument("lease_id")
    quarantine = sub.add_parser("quarantine")
    quarantine.add_argument("lease_id")
    args = parser.parse_args(argv)

    try:
        manager = WorktreeLeaseManager(
            args.project, workspace_root=args.workspace_root
        )
        if args.command == "list":
            payload = [lease.contract_view() for lease in manager.list()]
        elif args.command == "inspect":
            payload = manager.refresh(args.lease_id).contract_view()
        elif args.command == "release":
            payload = manager.release(args.lease_id).contract_view()
        else:
            payload = manager.quarantine(args.lease_id).contract_view()
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    except WorkspaceLeaseError as exc:
        print(f"LEASE ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
