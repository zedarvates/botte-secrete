"""CLI for Auto-Distiller — distillation cloud → micro-NN.

Usage:
    python -m skills.auto_distill.cli record "input" "decision"
    python -m skills.auto_distill.cli format
    python -m skills.auto_distill.cli train --model my_model
    python -m skills.auto_distill.cli evaluate
"""
from __future__ import annotations

import argparse
import json
import sys

from skills.console_utf8 import force_utf8
from skills.auto_distill.pipeline import DistillationPipeline


def cmd_record(args: argparse.Namespace):
    pipe = DistillationPipeline()
    pipe.record(args.input, args.decision, confidence=args.confidence,
                agent_type=args.agent)
    return 0


def cmd_format(args: argparse.Namespace):
    pipe = DistillationPipeline()
    data = pipe.format_training_data(args.min_confidence)
    print(json.dumps(data, indent=2))
    return 0


def cmd_train(args: argparse.Namespace):
    pipe = DistillationPipeline()
    result = pipe.train(args.model, args.min_confidence)
    return 0 if result else 1


def cmd_evaluate(_args: argparse.Namespace):
    pipe = DistillationPipeline()
    print(json.dumps(pipe.evaluate(), indent=2))
    return 0


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="auto_distill", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("record", help="Record a cloud decision")
    s.add_argument("input", help="Input text")
    s.add_argument("decision", help="Decision made")
    s.add_argument("--confidence", type=float, default=1.0)
    s.add_argument("--agent", default="")
    s.set_defaults(func=cmd_record)

    s2 = sub.add_parser("format", help="Format training data")
    s2.add_argument("--min-confidence", type=float, default=0.8)
    s2.set_defaults(func=cmd_format)

    s3 = sub.add_parser("train", help="Train a micro-NN")
    s3.add_argument("--model", default="auto_distilled")
    s3.add_argument("--min-confidence", type=float, default=0.8)
    s3.set_defaults(func=cmd_train)

    sub.add_parser("evaluate", help="Evaluate distillation").set_defaults(func=cmd_evaluate)

    args = p.parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
