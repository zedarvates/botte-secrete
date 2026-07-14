"""CLI for delta-only and final verification selection."""
from __future__ import annotations

from pathlib import Path

from skills.harness_delta.verifier import DeltaVerifier

__all__ = ["DeltaVerifier"]


def main(argv=None) -> int:
    from skills.console_utf8 import force_utf8
    force_utf8()
    import argparse
    parser = argparse.ArgumentParser(prog="harness_delta", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    verifier = DeltaVerifier()
    snapshot = sub.add_parser("snapshot")
    snapshot.add_argument("section")
    snapshot.add_argument("--content", required=True)
    snapshot.set_defaults(func=lambda args: _snapshot(verifier, args))
    verify = sub.add_parser("verify")
    verify.add_argument("--new", required=True)
    verify.add_argument("--final", action="store_true")
    verify.set_defaults(func=lambda args: _verify(verifier, args))
    risk = sub.add_parser("risk")
    risk.add_argument("--section", required=True)
    risk.add_argument("--score", type=float, default=0.5)
    risk.set_defaults(func=lambda args: _risk(verifier, args))
    args = parser.parse_args(argv)
    return args.func(args) or 0


def _snapshot(verifier: DeltaVerifier, args) -> None:
    verifier.snapshot(args.section, args.content)
    print(f"Snapshotted '{args.section}'")


def _verify(verifier: DeltaVerifier, args) -> None:
    content = Path(args.new).read_text(encoding="utf-8")
    for item in verifier.sections_to_verify({"content": content}, final=args.final):
        print(f"{item['section']}: {item['reason']}")


def _risk(verifier: DeltaVerifier, args) -> None:
    verifier.set_risk(args.section, args.score)
    print(f"Risk score for '{args.section}': {args.score}")


if __name__ == "__main__":
    raise SystemExit(main())
