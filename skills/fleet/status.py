#!/usr/bin/env python3
"""Fleet aggregate status with sorting — a *view* over the canonical fleet
registry (skills.dashboard.fleet, ~/.botte/fleet.json). This module used to
read its own registry (~/.botte/fleet/*.json), which silently diverged from
the one `dashboard fleet add` writes; now there is one source of truth.

    python -m skills.fleet.status [--sort tokens_saved|loc|fixes]
"""

from __future__ import annotations

import argparse
import json


def fleet_status(sort: str = "tokens_saved") -> dict:
    from skills.dashboard import fleet
    agg = fleet.aggregate()

    projects = []
    for proj in agg.get("projects", []):
        path = proj.get("project", "")
        projects.append({
            "name": path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1],
            "path": path,
            "loc": proj.get("loc", 0) or 0,
            "tokens_saved": proj.get("tokens_saved", 0) or 0,
            "fixes": proj.get("outstanding_fixes", 0) or 0,
        })

    key = sort if sort in ("tokens_saved", "loc", "fixes") else "tokens_saved"
    projects.sort(key=lambda x: x.get(key, 0), reverse=True)
    return {"projects": projects, "count": len(projects), "sort": key,
            "errored": agg.get("totals", {}).get("projects_errored", 0)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--sort", default="tokens_saved", choices=["tokens_saved", "loc", "fixes"])
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    status = fleet_status(args.sort)
    if args.json:
        print(json.dumps(status, indent=2))
        return

    print(f"Fleet — {status['count']} project(s)  (sort: {status['sort']})")
    for proj in status["projects"]:
        print(f"   {proj['name']:<30} {proj['loc']:>6} LOC  "
              f"saved={proj['tokens_saved']}  fixes={proj['fixes']}")


if __name__ == "__main__":
    main()
