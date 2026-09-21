#!/usr/bin/env python3
"""Observe RTK and explicit Ponytail installations without installing either.

Python 3.10+, standard library only. RTK is invoked with --version only;
Ponytail metadata is read without executing its plugin or hooks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


REFERENCE = Path(__file__).resolve().parents[1] / "configs" / "external-tools.json"
RELEASE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
PONYTAIL_MANIFESTS = {
    "package.json": "@dietrichgebert/ponytail",
    ".claude-plugin/plugin.json": "ponytail",
    ".codex-plugin/plugin.json": "ponytail",
}


def version_status(observed: str, reference: str) -> str:
    """Compare stable numeric releases; leave prereleases/builds for review."""
    if not RELEASE.fullmatch(observed) or not RELEASE.fullmatch(reference):
        return "unrecognized_version"
    actual = tuple(map(int, observed.split(".")))
    expected = tuple(map(int, reference.split(".")))
    if actual == expected:
        return "matches_reference"
    return "older_than_reference" if actual < expected else "newer_than_reference"


def inspect_rtk(reference: str, binary: str | None = None) -> dict:
    executable = binary or shutil.which("rtk")
    result = {"reference_version": reference, "observed_version": None,
              "executable": executable, "version_status": "not_found_on_path",
              "compatibility": "not_tested"}
    if not executable:
        return result
    try:
        proc = subprocess.run(
            [executable, "--version"], stdin=subprocess.DEVNULL,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=5, shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {**result, "version_status": "probe_failed", "error": type(exc).__name__}
    if proc.returncode != 0:
        return {**result, "version_status": "probe_failed", "exit_code": proc.returncode}
    match = re.fullmatch(r"rtk\s+(\S+)", proc.stdout.strip())
    if not match:
        return {**result, "version_status": "unexpected_version_output"}
    version = match.group(1)
    return {**result, "observed_version": version,
            "version_status": version_status(version, reference)}


def inspect_ponytail(root: Path, reference: str) -> dict:
    root = root.expanduser().resolve()
    result = {"root": str(root), "reference_version": reference,
              "observed_version": None, "version_status": "metadata_not_found",
              "compatibility": "not_tested", "active_in_agent": "not_checked",
              "manifests": []}
    versions: set[str] = set()
    for relative, expected_name in PONYTAIL_MANIFESTS.items():
        path = root / relative
        try:
            # Bound metadata reads; plugin code and lifecycle hooks are never loaded.
            with path.open("rb") as handle:
                raw = handle.read(65537)
        except FileNotFoundError:
            continue
        except OSError as exc:
            return {**result, "version_status": "metadata_error", "error": type(exc).__name__}
        if len(raw) > 65536:
            return {**result, "version_status": "metadata_error", "error": "metadata_too_large"}
        try:
            data = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeError, ValueError):
            return {**result, "version_status": "metadata_error", "error": "invalid_json"}
        if (not isinstance(data, dict) or data.get("name") != expected_name
                or not isinstance(data.get("version"), str)):
            return {**result, "version_status": "metadata_error", "error": "identity_or_version_mismatch"}
        versions.add(data["version"])
        result["manifests"].append({"file": relative, "version": data["version"],
                                    "sha256": hashlib.sha256(raw).hexdigest()})
    if len(versions) > 1:
        return {**result, "version_status": "conflicting_metadata"}
    if not versions:
        return result
    version = versions.pop()
    return {**result, "observed_version": version,
            "version_status": version_status(version, reference)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--machine-label", default="unspecified")
    parser.add_argument("--rtk-binary", help="Explicit RTK executable, otherwise use PATH")
    parser.add_argument("--ponytail-root", type=Path, action="append", default=[],
                        help="Installed plugin/package root; repeat for separate agent installations")
    args = parser.parse_args(argv)
    refs = json.loads(REFERENCE.read_text(encoding="utf-8"))
    report = {
        "schema_version": 1,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "machine_label": args.machine_label,
        "platform": platform.system(),
        "scope": "current_process_PATH_and_explicit_plugin_roots",
        "reference_verified_on": refs["verified_on"],
        "rtk": inspect_rtk(refs["tools"]["rtk"]["reference_version"], args.rtk_binary),
        "ponytail": [inspect_ponytail(root, refs["tools"]["ponytail"]["reference_version"])
                     for root in args.ponytail_root] or [{"version_status": "not_checked",
                         "reason": "No explicit plugin root supplied"}],
        "limits": ["Version observations do not certify source integrity or compatibility",
                   "Agent activation and other shells, users or hosts are not checked"],
    }
    print(json.dumps(report, ensure_ascii=True, indent=2))
    # This is an inventory, not a deployment gate. Read version_status in the JSON.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
