#!/usr/bin/env python3
"""Demo scripted scenarios — replay pre-recorded session for showcase.

    python -m skills.demo.scripted [--scenario web-frontend|security-audit]

Scenarios are pre-recorded event sequences that demonstrate Botte's routing
in different project types.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCENARIOS = {
    "web-frontend": {
        "name": "Web Frontend Project",
        "description": "React app, mostly formatting/lint tasks → local, occasional architecture → cloud",
        "events": [
            {"kind": "route", "mode": "local", "tier": "LOCAL", "reason": "format code → local"},
            {"kind": "route", "mode": "local", "tier": "LOCAL", "reason": "add type hints → local"},
            {"kind": "route", "mode": "cloud", "tier": "STANDARD", "reason": "design component hierarchy → cloud"},
            {"kind": "route", "mode": "local", "tier": "LOCAL", "reason": "fix lint → local"},
            {"kind": "escalate", "reason": "verification failed on complex refactor"},
            {"kind": "route", "mode": "local", "tier": "CHEAP", "reason": "NN belt → local"},
        ],
        "savings": "4/6 local (67%)",
    },
    "security-audit": {
        "name": "Security Audit",
        "description": "Penetration testing, mostly cloud-requiring tasks",
        "events": [
            {"kind": "route", "mode": "cloud", "tier": "STANDARD", "reason": "taint analysis → cloud"},
            {"kind": "route", "mode": "cloud", "tier": "PREMIUM", "reason": "architecture review → premium"},
            {"kind": "route", "mode": "local", "tier": "LOCAL", "reason": "pattern scan → local (deterministic)"},
            {"kind": "escalate", "reason": "cwe_kb enrichment needed"},
            {"kind": "route", "mode": "cloud", "tier": "STANDARD", "reason": "secrets audit → cloud"},
        ],
        "savings": "1/5 local (20% — security-heavy workload)",
    },
}


def main():
    scenario = sys.argv[1] if len(sys.argv) > 1 else "web-frontend"
    if scenario not in SCENARIOS:
        print(f"Unknown scenario: {scenario}. Available: {list(SCENARIOS)}")
        return
    s = SCENARIOS[scenario]
    print(f"🎬 Demo: {s['name']}")
    print(f"   {s['description']}")
    print()
    for e in s["events"]:
        kind = e.get("kind", "?")
        mode = e.get("mode", "")
        reason = e.get("reason", "")[:70]
        print(f"   [{kind}] {mode:6} — {reason}")
    print(f"\n   💰 {s['savings']}")


if __name__ == "__main__":
    main()
