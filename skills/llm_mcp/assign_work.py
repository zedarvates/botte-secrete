"""Normalize the MCP assignment formats before invoking the LPT solver."""

import math


def normalize_tasks(tasks: list) -> list[tuple[str, float]]:
    result = []
    for task in tasks:
        if isinstance(task, str):
            if ":" in task:
                name, raw_cost = task.rsplit(":", 1)
            else:
                name, raw_cost = task, 1
        elif isinstance(task, (list, tuple)) and len(task) == 2:
            name, raw_cost = task
        else:
            raise ValueError("task must be a name, name:cost, or [name, cost] pair")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("task name must be a non-empty string")
        if isinstance(raw_cost, bool):
            raise ValueError("task cost must be a finite non-negative number")
        try:
            cost = float(raw_cost)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("task cost must be a finite non-negative number") from exc
        if not math.isfinite(cost) or cost < 0:
            raise ValueError("task cost must be a finite non-negative number")
        if isinstance(raw_cost, int) and not isinstance(raw_cost, bool) and int(cost) != raw_cost:
            raise ValueError("integer task cost loses precision in float conversion")
        if isinstance(raw_cost, str):
            from decimal import Decimal, InvalidOperation
            try:
                if Decimal(raw_cost) != Decimal(str(cost)):
                    raise ValueError("task cost loses precision in float conversion")
            except InvalidOperation:
                raise ValueError("task cost must be numeric") from None
        result.append((name, cost))
    return result


def has_unsupported_precision(tasks: list) -> bool:
    """Check original text before float normalization; numeric JSON is already parsed."""
    from decimal import Decimal
    for task in tasks:
        if isinstance(task, str):
            raw = task.rsplit(":", 1)[1] if ":" in task else 1
        else:
            raw = task[1]
        d = Decimal(str(raw))
        parts = d.as_tuple()
        digits = list(parts.digits)
        exponent = parts.exponent
        if not any(digits):
            continue
        while digits and digits[-1] == 0:
            digits.pop()
            exponent += 1
        if exponent < -4:
            return True
    return False
