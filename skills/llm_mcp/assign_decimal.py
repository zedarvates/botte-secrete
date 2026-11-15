"""Isolated decimal adapter for the installed bounded solver, at most four places."""
import math
from decimal import Decimal
from skills.llm_mcp.decimal_integer_core import assign_with_search as integer_search


def assign_decimal(tasks, workers, assign_balanced, budget_ms=10):
    # A caller's Decimal context must not round input or corrupt the proof.
    from decimal import Context, localcontext
    with localcontext(Context(prec=64)):
        return _assign_decimal(tasks, workers, assign_balanced, budget_ms)


def _assign_decimal(tasks, workers, assign_balanced, budget_ms=10):
    baseline = assign_balanced(tasks, workers)
    if budget_ms <= 0:
        return baseline, {'mode': 'lpt', 'reason': 'budget_disabled', 'optimal': False}
    if (not workers or len(workers) > 4 or len(set(workers)) != len(workers)
            or not tasks or len(tasks) > 12):
        return baseline, {'mode': 'lpt', 'reason': 'unsupported_scope', 'optimal': False}
    scale = Decimal(10000)
    scaled = []
    for name, value in tasks:
        if (not isinstance(value, (int, float)) or isinstance(value, bool)
                or not math.isfinite(value) or value < 0 or value > 1000000):
            return baseline, {'mode': 'lpt', 'reason': 'unsupported_scope', 'optimal': False}
        number = Decimal(str(value)) * scale
        if number != number.to_integral_value():
            return baseline, {'mode': 'lpt', 'reason': 'unsupported_precision', 'optimal': False}
        scaled.append((name, int(number)))
    # Keep integer sums exactly representable by binary float (at most 12 * 1e10).
    divisor = math.gcd(*(value for _, value in scaled)) or 1
    reduced = [(name, value // divisor) for name, value in scaled]
    if any(value > 10000000000 for _, value in reduced):
        return baseline, {'mode': 'lpt', 'reason': 'unsupported_scale', 'optimal': False}
    candidate, meta = integer_search(reduced, workers, assign_balanced, budget_ms=budget_ms)
    if not meta['optimal']:
        return baseline, meta
    best = Decimal(str(candidate['makespan'])) * divisor / scale
    old = max(sum((Decimal(str(t['cost'])) for t in group), Decimal(0))
              for group in baseline['assignment'].values())
    if best >= old:
        return baseline, {'mode': 'lpt', 'reason': 'already_optimal', 'optimal': True}
    result = dict(baseline)
    result['assignment'] = {w: [{'task': t['task'], 'cost': float(Decimal(str(t['cost'])) * divisor / scale)}
                                for t in group] for w, group in candidate['assignment'].items()}
    result['loads'] = {w: round(sum(t['cost'] for t in group), 4)
                       for w, group in result['assignment'].items()}
    result['makespan'] = round(max(result['loads'].values()), 4)
    return result, {'mode': 'exact', 'reason': 'improved', 'optimal': True}
