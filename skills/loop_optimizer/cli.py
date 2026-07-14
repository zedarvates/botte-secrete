"""Inspect and record Loop Optimizer decisions without executing tools."""

from __future__ import annotations

import json

from skills.loop_optimizer.controller import LoopController
from skills.loop_optimizer.models import LoopRequest, LoopState


def _controller() -> LoopController:
    return LoopController()


def _request(args) -> LoopRequest:
    return LoopRequest(args.loop_id, args.goal, max_iterations=args.max_iterations,
                       max_total_tokens=args.max_total_tokens,
                       max_cloud_tokens=args.max_cloud_tokens,
                       criticality=args.criticality,
                       allowed_tools=tuple(args.tools))


def _state(args) -> LoopState:
    return LoopState(args.loop_id, iteration=args.iteration,
                     context_tokens=args.context_tokens,
                     execution_tokens=args.execution_tokens,
                     verification_tokens=args.verification_tokens,
                     cloud_tokens=args.cloud_tokens)


def main(argv=None) -> int:
    from skills.console_utf8 import force_utf8
    force_utf8()
    import argparse
    parser = argparse.ArgumentParser(prog="loop_optimizer", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("run", "explain"):
        command = sub.add_parser(name)
        command.add_argument("loop_id")
        command.add_argument("goal")
        command.add_argument("--tools", nargs="*", default=[])
        command.add_argument("--max-iterations", type=int, default=5)
        command.add_argument("--max-total-tokens", type=int, default=8000)
        command.add_argument("--max-cloud-tokens", type=int, default=2000)
        command.add_argument("--criticality", type=float, default=0.5)
        command.add_argument("--iteration", type=int, default=0)
        command.add_argument("--context-tokens", type=int, default=0)
        command.add_argument("--execution-tokens", type=int, default=0)
        command.add_argument("--verification-tokens", type=int, default=0)
        command.add_argument("--cloud-tokens", type=int, default=0)
        command.set_defaults(func=_run if name == "run" else _explain)
    sub.add_parser("stats").set_defaults(func=_stats)
    replay = sub.add_parser("replay")
    replay.add_argument("loop_id")
    replay.set_defaults(func=_replay)
    args = parser.parse_args(argv)
    return args.func(args) or 0


def _run(args) -> None:
    controller = _controller()
    decision = controller.decide(_request(args), _state(args))
    print(json.dumps(decision.to_dict(), ensure_ascii=False, separators=(",", ":")))


def _explain(args) -> None:
    controller = _controller()
    print(json.dumps(controller.explain(_request(args), _state(args)), ensure_ascii=False,
                     separators=(",", ":")))


def _stats(_args) -> None:
    controller = _controller()
    print(json.dumps(controller.ledger.summarize(controller.ledger.read()),
                     ensure_ascii=False, separators=(",", ":")))


def _replay(args) -> None:
    controller = _controller()
    print(json.dumps(controller.ledger.read(args.loop_id), ensure_ascii=False,
                     separators=(",", ":")))


if __name__ == "__main__":
    raise SystemExit(main())
