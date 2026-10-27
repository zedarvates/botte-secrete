#!/usr/bin/env python3
"""Focused Quality Compass card, privacy, and accessibility tests."""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

from scripts.generate_public_dashboard import public_metrics
from skills.dashboard.quality_compass import quality_compass_card
from skills.trajectory.quality import record_verified


def _record(project: Path, task: str, *, route: str = "deterministic",
            verdict: str = "PASS", model: str = "", harness: str = "") -> None:
    record_verified(
        task,
        project_root=project,
        route=route,
        verdict=verdict,
        verified_by="pytest:quality-card",
        evidence_refs=(f"pytest:{route}:{verdict.casefold()}",),
        quality_score={"FAIL": 0.1, "UNCERTAIN": 0.4, "PASS": 0.8, "PASS_ROBUST": 1.0}[verdict],
        model=model,
        harness=harness,
        duration_ms=25,
        cost_usd=0,
        tokens=12,
    )


def _outcome(project: Path, *, status: str = "ABSTAINED",
             approval_required: bool = False) -> None:
    root = project / ".botte"
    root.mkdir(parents=True, exist_ok=True)
    now = time.time()
    row = {
        "schema": "botte.quality-outcome/v1",
        "id": "qo_0123456789abcdef",
        "recorded_at": "2026-08-26T00:00:00+00:00",
        "timestamp": now,
        "route": "human" if approval_required else "local",
        "status": status,
        "risk": "high" if approval_required else "standard",
        "abstained": status == "ABSTAINED",
        "escalated": status == "ESCALATED",
        "approval_required": approval_required,
        "memory_mb": 384.0,
        "energy_wh": 0.03,
        "tool_versions": {"harness": "wave2"},
        "model": "local-fixture",
        "harness": "quality-fixture",
        "shadow_only": True,
        "activation_allowed": False,
        "raw_task_stored": False,
    }
    (root / "quality-outcomes.jsonl").write_text(
        json.dumps(row) + "\n", encoding="utf-8"
    )


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(map(_all_keys, value.values())))
    if isinstance(value, list):
        return set().union(*(map(_all_keys, value))) if value else set()
    return set()


def main() -> int:
    state = [0, 0]

    def ok(message: str, condition: bool) -> None:
        print(f"  [{'PASS' if condition else 'FAIL'}] {message}")
        state[0 if condition else 1] += 1

    print("== quality compass dashboard tests ==")

    with tempfile.TemporaryDirectory() as directory:
        project = Path(directory)
        card = quality_compass_card(project)
        ok("empty state gives one deterministic safe action",
           card["state"] == "empty" and not card["activation_allowed"]
           and "deterministic" in card["next_action"].casefold())

        _record(project, "collect one verified result")
        card = quality_compass_card(project)
        ok("collecting state reports measured progress",
           card["state"] == "collecting"
           and card["summary"]["verified_samples"] == 1
           and card["summary"]["grounding_coverage"] == 0.2)

    with tempfile.TemporaryDirectory() as directory:
        project = Path(directory)
        for index in range(5):
            _record(project, f"grounded recurring fixture {index}",
                    route="local" if index % 2 else "deterministic",
                    model="micro-local", harness="fixture-harness")
        card = quality_compass_card(project)
        ok("grounded state exposes route comparison progressively",
           card["state"] == "grounded"
           and len(card["route_comparison"]) == 2
           and len(card["supporting_evidence"]) == 5)

        stale = quality_compass_card(project, now=time.time() + 8 * 24 * 60 * 60)
        ok("stale evidence prescribes a fresh deterministic replay",
           stale["state"] == "stale" and "replay" in stale["next_action"].casefold())

    with tempfile.TemporaryDirectory() as directory:
        project = Path(directory)
        for index in range(5):
            _record(project, f"conflict fixture {index}")
        _record(project, "conflict fixture 0", route="local", verdict="FAIL")
        card = quality_compass_card(project)
        ok("conflicting state detects incompatible verified routes",
           card["state"] == "conflicting"
           and card["drift"]["conflicting_tasks"] == 1)

    with tempfile.TemporaryDirectory() as directory:
        project = Path(directory)
        _outcome(project, status="APPROVAL_REQUIRED", approval_required=True)
        card = quality_compass_card(project)
        ok("high-risk outcome displays the human gate",
           card["state"] == "human_gated" and card["human_gate"]
           and not card["activation_allowed"])

    with tempfile.TemporaryDirectory() as directory:
        project = Path(directory)
        _record(project, "PRIVATE_TASK_CANARY dashboard path")
        _outcome(project)
        card = quality_compass_card(project)
        encoded = json.dumps(card)
        ok("local card omits task fingerprints and storage paths",
           "PRIVATE_TASK_CANARY" not in encoded
           and "task_fingerprint" not in encoded
           and str(project) not in encoded)
        ok("Wave 2 envelopes supply abstention and resource details",
           card["summary"]["abstention_rate"] == 1.0
           and card["resources"]["mean_memory_mb"] == 384.0
           and card["source_contract"] == "botte.quality-outcome/v1")

    public = public_metrics()
    banned_keys = {"task", "task_fingerprint", "execution_fingerprint", "storage",
                   "path", "evidence_refs", "supporting_evidence"}
    ok("public snapshot contains no local task, fingerprint, path, or evidence detail",
       not (banned_keys & _all_keys(public))
       and public["quality_compass"]["state"] == "private")

    html = Path(__file__).with_name("index.html").read_text(encoding="utf-8")
    ok("card uses native progressive disclosure and accessible labelling",
       'aria-labelledby="quality-title"' in html
       and '<details class="quality-details"' in html
       and "<summary>Inspect evidence" in html
       and 'scope="col"' in html
       and "innerHTML" not in html)
    ok("card has narrow-screen and reduced-motion behavior",
       "@media (max-width: 560px)" in html
       and ".quality-line { grid-template-columns: 1fr" in html
       and "prefers-reduced-motion" in html)

    print(f"\nRESULT: {state[0]} passed, {state[1]} failed")
    return 0 if state[1] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
