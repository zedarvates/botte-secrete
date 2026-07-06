"""Self-Budgeting Agents — agents qui gèrent eux-mêmes leur budget token.

Chaque agent reçoit un budget token et doit décider comment l'utiliser :
- Réduire son propre contexte si nécessaire
- Compresser ses propres outputs
- Décider de ne pas répondre si pas pertinent
- Renvoyer un delta-only output

Usage:
    python -m skills.self_budget.cli audit "task" --budget 2000
    python -m skills.self_budget.cli compress "output"
    python -m skills.self_budget.cli delta "new_output" "previous_output"
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from typing import Optional

from skills.console_utf8 import force_utf8


@dataclass
class Budget:
    """Token budget for an agent."""
    total: int
    used: int = 0
    reserved: int = 100  # Reserve for critical operations

    @property
    def remaining(self) -> int:
        return self.total - self.used - self.reserved

    @property
    def exhausted(self) -> bool:
        return self.remaining <= 0

    def spend(self, amount: int) -> bool:
        if self.remaining >= amount:
            self.used += amount
            return True
        return False


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def compress_output(text: str, target_tokens: int) -> str:
    """Compress output to fit within budget."""
    if estimate_tokens(text) <= target_tokens:
        return text

    lines = text.split("\n")
    # Keep head + tail
    head = lines[:5]
    tail = lines[-3:]
    compressed = "\n".join(head + [f"... ({len(lines) - 8} lines omitted)"] + tail)

    # Still too long ? Truncate
    if estimate_tokens(compressed) > target_tokens:
        compressed = text[:target_tokens * 4] + "\n... [truncated]"

    return compressed


def compute_delta(new: str, old: str) -> str:
    """Compute delta between new and previous output."""
    if new == old:
        return "[no change]"

    new_lines = new.split("\n")
    old_lines = old.split("\n")

    # Simple diff: show only changed lines
    delta = []
    max_len = max(len(new_lines), len(old_lines))
    for i in range(max_len):
        n = new_lines[i] if i < len(new_lines) else ""
        o = old_lines[i] if i < len(old_lines) else ""
        if n != o:
            if o and n:
                delta.append(f"- {o}")
                delta.append(f"+ {n}")
            elif n:
                delta.append(f"+ {n}")
            elif o:
                delta.append(f"- {o}")

    result = "\n".join(delta[:20])  # Max 20 changed lines
    if len(delta) > 20:
        result += f"\n... ({len(delta) - 20} more changes)"

    return result


def cmd_audit(args: argparse.Namespace):
    """Audit if an agent can complete a task within budget."""
    budget = Budget(total=args.budget)
    task_cost = estimate_tokens(args.task)

    print(f"Budget: {budget.total} tokens")
    print(f"Task cost: ~{task_cost} tokens")
    print(f"Remaining after task: {budget.remaining - task_cost} tokens")
    print(f"Feasible: {'✅' if task_cost <= budget.remaining else '❌'}")

    if task_cost > budget.remaining:
        suggested = compress_output(args.task, budget.remaining)
        print(f"\nSuggested compressed task ({estimate_tokens(suggested)} tok):")
        print(suggested[:200])


def cmd_compress(args: argparse.Namespace):
    """Compress output to fit budget."""
    compressed = compress_output(args.output, args.target)
    print(f"Original: {estimate_tokens(args.output)} tok")
    print(f"Compressed: {estimate_tokens(compressed)} tok")
    print(f"---")
    print(compressed)


def cmd_delta(args: argparse.Namespace):
    """Compute delta between outputs."""
    delta = compute_delta(args.new, args.previous)
    print(f"Delta size: {estimate_tokens(delta)} tok")
    print(f"---")
    print(delta)


def main(argv=None) -> int:
    force_utf8()
    p = argparse.ArgumentParser(prog="self_budget", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("audit", help="Audit budget feasibility")
    s.add_argument("task", help="Task description")
    s.add_argument("--budget", type=int, default=2000, help="Token budget")
    s.set_defaults(func=cmd_audit)

    s2 = sub.add_parser("compress", help="Compress output")
    s2.add_argument("output", help="Output to compress")
    s2.add_argument("--target", type=int, default=500, help="Target tokens")
    s2.set_defaults(func=cmd_compress)

    s3 = sub.add_parser("delta", help="Compute delta")
    s3.add_argument("new", help="New output")
    s3.add_argument("previous", help="Previous output")
    s3.set_defaults(func=cmd_delta)

    args = p.parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
