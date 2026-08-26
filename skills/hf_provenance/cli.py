"""Audit a downloaded Hugging Face model snapshot against Botte source."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .audit import audit_snapshot
from skills.nn_audit import audit_models


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot_dir", type=Path, help="downloaded Hub models directory")
    parser.add_argument(
        "--source-dir", type=Path, default=Path("skills/botte_nn/models"),
        help="authoritative source models directory",
    )
    parser.add_argument("--hub-repo", default="zedgamer/botte-nano-nn")
    parser.add_argument("--hub-revision")
    parser.add_argument("--source-revision")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    grounding = audit_models(args.source_dir.parent)
    verdicts = {item["model"]: item["verdict"] for item in grounding.get("models", [])}
    report = audit_snapshot(
        args.source_dir,
        args.snapshot_dir,
        hub_repo=args.hub_repo,
        hub_revision=args.hub_revision,
        source_revision=args.source_revision,
        grounding_verdicts=verdicts,
    )
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["publish_weights_allowed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
