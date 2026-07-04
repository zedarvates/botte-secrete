"""Lightweight SBOM scanner — parse dependency files (stdlib only).

    python -m skills.sbom.scan <project>

Reads requirements.txt / Cargo.toml / package.json. 0 cloud tokens.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def scan(project: str | Path) -> dict:
    project = Path(project).resolve()
    deps: dict[str, int] = {}

    for req in project.rglob("requirements*.txt"):
        if ".venv" in str(req) or "node_modules" in str(req):
            continue
        for line in req.read_text(errors="replace").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                pkg = re.split(r"[=<>~!]", line)[0].strip()
                deps[pkg] = deps.get(pkg, 0) + 1

    for cargo in project.rglob("Cargo.toml"):
        text = cargo.read_text(errors="replace")
        for m in re.finditer(r'^(\w[\w-]*)\s*=\s*"[^"]*"', text, re.MULTILINE):
            deps[m.group(1)] = deps.get(m.group(1), 0) + 1

    for pkg_json in project.rglob("package.json"):
        if "node_modules" in str(pkg_json):
            continue
        try:
            data = json.loads(pkg_json.read_text())
            for section in ("dependencies", "devDependencies"):
                for name in data.get(section, {}):
                    deps[name] = deps.get(name, 0) + 1
        except (json.JSONDecodeError, OSError):
            pass

    return {
        "project": str(project),
        "dependencies": len(deps),
        "packages": sorted(deps.keys()),
        "cloud_tokens": 0,
    }


if __name__ == "__main__":
    project = sys.argv[1] if len(sys.argv) > 1 else "."
    result = scan(project)
    print(f"SBOM: {result['dependencies']} packages")
    for pkg in result["packages"]:
        print(f"  {pkg}")
