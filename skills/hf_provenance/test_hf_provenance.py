#!/usr/bin/env python3
"""Hermetic tests for the Hugging Face snapshot provenance gate."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .audit import audit_snapshot


def _ok(message: str, condition: bool, state: list[int]) -> None:
    print(f"  [{'PASS' if condition else 'FAIL'}] {message}")
    state[0 if condition else 1] += 1


def _write(root: Path, name: str, payload: dict) -> None:
    (root / name).write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def main() -> int:
    state = [0, 0]
    print("== Hugging Face provenance tests ==")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "source"
        hub = root / "hub"
        source.mkdir()
        hub.mkdir()
        grounded = {"weights": [1, 2], "trained_on": "verified corpus"}
        _write(source, "grounded.json", grounded)
        _write(hub, "grounded.json", grounded)
        clean = audit_snapshot(
            source, hub, hub_revision="abc", source_revision="def",
            grounding_verdicts={"grounded": "grounded"},
        )
        _ok("exact grounded snapshot passes", clean["publish_weights_allowed"], state)
        _ok("revisions are recorded", clean["hub_revision"] == "abc" and clean["source_revision"] == "def", state)

        _write(hub, "grounded.json", {"weights": [9], "trained_on": "unknown"})
        mismatch = audit_snapshot(source, hub)
        _ok("hash mismatch blocks publication", not mismatch["publish_weights_allowed"], state)
        _ok("mismatch names the file", mismatch["comparison"]["hash_mismatches"] == ["grounded.json"], state)

        _write(hub, "grounded.json", grounded)
        _write(hub, "legacy.json", {"weights": [0]})
        extra = audit_snapshot(source, hub)
        _ok("Hub-only file blocks publication", extra["comparison"]["hub_only"] == ["legacy.json"], state)

        (hub / "legacy.json").unlink()
        _write(source, "unproven.json", {"weights": [0]})
        missing = audit_snapshot(source, hub)
        _ok("incomplete Hub inventory blocks publication", missing["comparison"]["missing_on_hub"] == ["unproven.json"], state)
        _ok("missing source provenance is explicit", missing["comparison"]["source_missing_provenance"] == ["unproven.json"], state)
        _ok("report remains JSON serialisable", isinstance(json.dumps(missing), str), state)

        unknown = audit_snapshot(
            source, hub, grounding_verdicts={"grounded": "grounded", "unproven": "unknown"}
        )
        _ok("non-grounded source model is an explicit block",
            unknown["comparison"]["source_not_grounded"] == ["unproven.json"], state)

    passed, failed = state
    print(f"\nRESULT: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
