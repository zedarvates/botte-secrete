"""Integration candidate: opt-in, bounded integer scheduling; runtime untouched."""
import math
import time


def assign_with_search(tasks, workers, assign_balanced, budget_ms=10, clock=time.perf_counter_ns):
    """Return (existing Botte response, metadata); normalized inputs expected.

    On unsupported input or timeout, return precisely the unmodified LPT response.
    Integers only: float rounding and heterogeneous/dependent work need separate design.
    """
    baseline = assign_balanced(tasks, workers)
    if not math.isfinite(budget_ms) or budget_ms <= 0:
        return baseline, {'mode': 'lpt', 'reason': 'budget_disabled', 'optimal': False}
    if (not workers or len(workers) > 4 or len(set(workers)) != len(workers)
            or not tasks or len(tasks) > 12
            or any(not isinstance(c, (int, float)) or isinstance(c, bool)
                   or not math.isfinite(c) or c < 0 or c > 10_000_000_000 or int(c) != c
                   for _, c in tasks)):
        return baseline, {'mode': 'lpt', 'reason': 'unsupported_scope', 'optimal': False}
    costs = [int(c) for _, c in tasks]
    count = len(workers)
    order = sorted(range(len(tasks)), key=lambda i: -costs[i])
    # Recover the initial assignment by index, even if task labels repeat.
    remaining = {w: [] for w in workers}
    loads0 = [0] * count
    for i in order:
        w = min(range(count), key=lambda j: (loads0[j], j))
        remaining[workers[w]].append(i)
        loads0[w] += costs[i]
    best_groups = [remaining[w] for w in workers]
    best = max(loads0)
    lower = max(max(costs), (sum(costs) + count - 1) // count)
    deadline = clock() + int(budget_ms * 1_000_000)
    loads = [0] * count
    groups = [[] for _ in workers]
    timed_out = False

    def visit(k):
        nonlocal best, best_groups, timed_out
        if clock() >= deadline:
            timed_out = True
            return
        if best == lower:
            return
        if k == len(order):
            best = max(loads)
            best_groups = [g.copy() for g in groups]
            return
        i = order[k]
        seen = set()
        for w in sorted(range(count), key=lambda j: loads[j]):
            if loads[w] in seen or loads[w] + costs[i] >= best:
                continue
            seen.add(loads[w])
            loads[w] += costs[i]
            groups[w].append(i)
            visit(k + 1)
            groups[w].pop()
            loads[w] -= costs[i]
            if timed_out or best == lower:
                return

    visit(0)
    if timed_out:
        return baseline, {'mode': 'lpt', 'reason': 'timeout', 'optimal': False}
    if best >= baseline['makespan']:
        return baseline, {'mode': 'lpt', 'reason': 'already_optimal', 'optimal': True}
    result = dict(baseline)
    result['assignment'] = {w: [{'task': tasks[i][0], 'cost': float(costs[i])}
                                for i in best_groups[j]] for j, w in enumerate(workers)}
    result['loads'] = {w: float(sum(costs[i] for i in best_groups[j]))
                       for j, w in enumerate(workers)}
    result['makespan'] = float(best)
    return result, {'mode': 'exact', 'reason': 'improved', 'optimal': True}
