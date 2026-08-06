"""CLI for Monte Cristo report templates, prompts, and validation."""

from __future__ import annotations

import argparse
import json
from typing import Sequence

from skills.console_utf8 import force_utf8
from skills.monte_cristo.contract import load_report, new_report, validate_report
from skills.monte_cristo.evaluation import benchmark, load_cases
from skills.monte_cristo.routing import TriggerContext, evaluate_trigger


def _dump(value: object, pretty: bool) -> str:
    if pretty:
        return json.dumps(value, ensure_ascii=False, indent=2)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def main(argv: Sequence[str] | None = None) -> int:
    force_utf8()
    parser = argparse.ArgumentParser(
        prog="monte_cristo",
        description="Independent strategic-outsider report tooling.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    template_parser = sub.add_parser("template", help="Print a valid report template")
    template_parser.add_argument("scope", help="Decision or project under review")
    template_parser.add_argument("--pretty", action="store_true")

    validate_parser = sub.add_parser("validate", help="Validate a report JSON file")
    validate_parser.add_argument("report", help="Path to a monte-cristo/v1 report")
    validate_parser.add_argument("--pretty", action="store_true")

    prompt_parser = sub.add_parser("prompt", help="Print the complete agent prompt")
    prompt_parser.add_argument("--project-root")

    route_parser = sub.add_parser("route", help="Evaluate whether the agent should run")
    route_parser.add_argument("request", help="User request or strategic decision")
    route_parser.add_argument("--material", action="store_true")
    route_parser.add_argument("--blue-red-stalled", action="store_true")
    route_parser.add_argument("--inherited-frame", action="store_true")
    route_parser.add_argument("--routine", action="store_true")
    route_parser.add_argument("--pretty", action="store_true")

    eval_parser = sub.add_parser("eval", help="Benchmark trigger quality")
    eval_parser.add_argument("--dataset")
    eval_parser.add_argument("--pretty", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "template":
        print(_dump(new_report(args.scope), args.pretty))
        return 0

    if args.command == "validate":
        try:
            report = load_report(args.report)
            errors = validate_report(report)
        except ValueError as exc:
            errors = getattr(exc, "errors", [str(exc)])
        result = {"ok": not errors, "schema": "monte-cristo/v1", "errors": errors}
        print(_dump(result, args.pretty))
        return 0 if not errors else 1

    if args.command == "route":
        context = TriggerContext(
            material_consequence=args.material,
            blue_red_stalled=args.blue_red_stalled,
            inherited_frame=args.inherited_frame,
            routine_scope=args.routine,
        )
        decision = evaluate_trigger(args.request, context)
        print(_dump(decision.to_dict(), args.pretty))
        return 0

    if args.command == "eval":
        cases = load_cases(args.dataset) if args.dataset else load_cases()
        result = benchmark(cases)
        print(_dump(result.to_dict(), args.pretty))
        return 0 if result.meets_activation_gate() else 1

    from skills.loader import load_agent

    print(load_agent("monte_cristo", project_root=args.project_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
