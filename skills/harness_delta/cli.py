"""Harness Delta Verifier — vérifie seulement les sections modifiées.

Dans une boucle rétroactive, le harness ne vérifie que :
- les nouvelles sections
- les sections modifiées depuis la dernière itération
- les sections à risque (score > seuil)

Au lieu de tout re-vérifier à chaque boucle.

Usage:
    python -m skills.harness_delta.cli verify --new "output.txt" --previous "output.old"
    python -m skills.harness_delta.cli risk --section "auth" --score 0.8
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


class DeltaVerifier:
    """Vérifie les deltas entre itérations successives."""

    def __init__(self):
        self.snapshots: dict[str, str] = {}  # section → hash
        self.risk_scores: dict[str, float] = {}  # section → risk (0-1)

    def snapshot(self, section: str, content: str):
        """Take a snapshot of a section."""
        self.snapshots[section] = hashlib.sha256(content.encode()).hexdigest()[:16]

    def has_changed(self, section: str, content: str) -> bool:
        """Check if a section changed since last snapshot."""
        current = hashlib.sha256(content.encode()).hexdigest()[:16]
        previous = self.snapshots.get(section)
        if previous is None:
            return True  # New section
        return current != previous

    def set_risk(self, section: str, score: float):
        """Set risk score for a section (0=safe, 1=risky)."""
        self.risk_scores[section] = max(0.0, min(1.0, score))

    def needs_verification(self, section: str, content: str,
                           risk_threshold: float = 0.3) -> tuple[bool, str]:
        """Determine if a section needs verification.

        Returns (needs_check, reason).
        """
        # Check if changed
        if self.has_changed(section, content):
            return (True, "section modified")

        # Check risk score
        risk = self.risk_scores.get(section, 0.0)
        if risk >= risk_threshold:
            return (True, f"risk score {risk:.2f} >= {risk_threshold}")

        return (False, "unchanged + low risk")

    def sections_to_verify(self, sections: dict[str, str],
                           risk_threshold: float = 0.3) -> list[dict]:
        """Filter sections to only those needing verification."""
        to_check = []
        skipped = 0

        for section, content in sections.items():
            needs, reason = self.needs_verification(section, content, risk_threshold)
            if needs:
                to_check.append({"section": section, "reason": reason})
            else:
                skipped += 1

        return to_check


def main(argv=None) -> int:
    from skills.console_utf8 import force_utf8
    force_utf8()

    import argparse
    p = argparse.ArgumentParser(prog="harness_delta", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    v = DeltaVerifier()

    s = sub.add_parser("snapshot", help="Snapshot a section")
    s.add_argument("section", help="Section name")
    s.add_argument("--content", required=True, help="Section content")
    s.set_defaults(func=lambda a: _snap(v, a))

    s2 = sub.add_parser("verify", help="Check what needs verification")
    s2.add_argument("--new", required=True, help="New content file")
    s2.add_argument("--previous", help="Previous content file")
    s2.set_defaults(func=lambda a: _verify(v, a))

    s3 = sub.add_parser("risk", help="Set risk score")
    s3.add_argument("--section", required=True, help="Section name")
    s3.add_argument("--score", type=float, default=0.5, help="Risk score")
    s3.set_defaults(func=lambda a: _risk(v, a))

    args = p.parse_args(argv)
    return 0


def _snap(v: DeltaVerifier, args):
    v.snapshot(args.section, args.content)
    print(f"✅ Snapshotted '{args.section}' ({len(args.content)} chars)")


def _verify(v: DeltaVerifier, args):
    new = Path(args.new).read_text() if args.new else sys.stdin.read()
    sections = {"content": new}
    to_check = v.sections_to_verify(sections)
    if to_check:
        for t in to_check:
            print(f"⚠️  {t['section']}: {t['reason']}")
    else:
        print("✅ Nothing to verify — all sections unchanged")


def _risk(v: DeltaVerifier, args):
    v.set_risk(args.section, args.score)
    print(f"✅ Risk score for '{args.section}': {args.score}")


if __name__ == "__main__":
    main()
