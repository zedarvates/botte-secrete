#!/usr/bin/env python3
"""Fleet aggregate status with sorting.

    python -m skills.fleet.status [--sort tokens_saved|loc|fixes]
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def fleet_status(sort: str = "tokens_saved") -> dict:
    fleet_dir = Path.home() / ".botte" / "fleet"
    projects = []

    if fleet_dir.exists():
        for reg_file in fleet_dir.glob("*.json"):
            try:
                reg = json.loads(reg_file.read_text())
                project_path = Path(reg.get("project", ""))
                if project_path.exists():
                    # Try to get checkup data
                    checkup_file = project_path / ".botte" / "reports" / "checkup-latest.json"
                    checkup = {}
                    if checkup_file.exists():
                        checkup = json.loads(checkup_file.read_text())
                    projects.append({
                        "name": project_path.name,
                        "path": str(project_path),
                        "loc": checkup.get("loc_total", 0),
                        "policy": checkup.get("policy_committed", False),
                        "drift": len(checkup.get("drift", [])),
                    })
            except (json.JSONDecodeError, OSError):
                continue

    key_map = {"tokens_saved": "loc", "loc": "loc", "fixes": "drift"}
    projects.sort(key=lambda x: x.get(key_map.get(sort, "loc"), 0), reverse=True)
    return {"projects": projects, "count": len(projects), "sort": sort}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--sort", default="tokens_saved", choices=["tokens_saved", "loc", "fixes"])
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    status = fleet_status(args.sort)
    if args.json:
        print(json.dumps(status, indent=2))
        return

    print(f"🚀 Fleet — {status['count']} project(s)  (sort: {status['sort']})")
    for proj in status["projects"]:
        print(f"   {proj['name']:<30} {proj['loc']:>6} LOC  drift={proj['drift']}  "
              f"policy={'✓' if proj['policy'] else '✗'}")


if __name__ == "__main__":
    main()
