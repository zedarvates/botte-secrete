"""Deterministic solvers — assignment, bin-packing, precedence scheduling.

The OR-Tools family, in stdlib: the structured decisions the system makes —
*spread work across the cluster*, *pack items under a capacity*, *order a plan's
steps under dependencies* — are classic combinatorial problems with exact or
well-known deterministic algorithms. No LLM "figure out the order/assignment"
call: 0 cloud tokens, repeatable.

  assign_balanced(tasks, workers)   balance load across workers (LPT greedy)
  bin_pack(items, capacity)         pack into the fewest bins (first-fit-decreasing)
  schedule(steps, deps)             topological order + parallel waves of a DAG

(For very large instances, `ortools` CP-SAT is a drop-in accelerator; these
stdlib solvers are the always-available path.)
"""

from __future__ import annotations

from typing import Optional


def assign_balanced(tasks: list, workers: list) -> dict:
    """Assign (name, cost) tasks across workers to balance load (LPT greedy).

    Longest-Processing-Time-first: a classic deterministic approximation that
    keeps the makespan (max worker load) within 4/3 of optimal. Returns the
    assignment, per-worker load, and the makespan.
    """
    if not workers:
        return {"error": "no workers"}
    norm = [(t if isinstance(t, (list, tuple)) else (t, 1)) for t in tasks]
    norm = [(str(n), float(c)) for n, c in norm]
    order = sorted(norm, key=lambda t: t[1], reverse=True)

    load = {w: 0.0 for w in workers}
    assignment = {w: [] for w in workers}
    for name, cost in order:
        # least-loaded worker; ties broken by worker order for determinism
        w = min(workers, key=lambda x: (load[x], workers.index(x)))
        assignment[w].append({"task": name, "cost": cost})
        load[w] += cost

    loads = {w: round(load[w], 4) for w in workers}
    makespan = round(max(load.values()), 4) if load else 0.0
    total = round(sum(c for _, c in norm), 4)
    return {"assignment": assignment, "loads": loads, "makespan": makespan,
            "total": total, "workers": len(workers), "cloud_tokens": 0}


def bin_pack(items: list, capacity: float) -> dict:
    """Pack (name, size) items into the fewest bins of `capacity` (FFD).

    First-Fit-Decreasing: sort items big→small, place each in the first bin it
    fits. Deterministic; near-optimal bin count. Oversized items get their own
    flagged bin.
    """
    if capacity <= 0:
        return {"error": "capacity must be > 0"}
    norm = [(t if isinstance(t, (list, tuple)) else (t, 1)) for t in items]
    norm = [(str(n), float(s)) for n, s in norm]
    order = sorted(norm, key=lambda t: t[1], reverse=True)

    bins: list = []          # each: {"items": [...], "used": float}
    oversize: list = []
    for name, size in order:
        if size > capacity:
            oversize.append({"task": name, "size": size})
            continue
        placed = False
        for b in bins:
            if b["used"] + size <= capacity + 1e-9:
                b["items"].append({"task": name, "size": size})
                b["used"] = round(b["used"] + size, 4)
                placed = True
                break
        if not placed:
            bins.append({"items": [{"task": name, "size": size}], "used": size})

    return {"bins": bins, "bin_count": len(bins), "capacity": capacity,
            "oversize": oversize, "cloud_tokens": 0}


def schedule(steps: list, deps: Optional[dict] = None) -> dict:
    """Topologically order steps under precedence `deps` + group parallel waves.

    deps = {step: [prerequisite, …]}. Returns a valid linear order and the waves
    (each wave's steps have all prerequisites satisfied by earlier waves, so they
    can run in parallel). Detects cycles. Exact, deterministic, 0 cloud tokens.
    """
    steps = list(dict.fromkeys(steps))  # de-dup, keep order
    deps = {k: list(v) for k, v in (deps or {}).items()}
    stepset = set(steps)

    # Only count prerequisites that are themselves steps.
    indeg = {s: 0 for s in steps}
    children: dict = {s: [] for s in steps}
    for s in steps:
        for pre in deps.get(s, []):
            if pre in stepset and pre != s:
                indeg[s] += 1
                children[pre].append(s)

    order: list = []
    waves: list = []
    ready = sorted([s for s in steps if indeg[s] == 0], key=steps.index)
    while ready:
        wave = ready
        waves.append(list(wave))
        order.extend(wave)
        nxt: list = []
        for s in wave:
            for c in children[s]:
                indeg[c] -= 1
                if indeg[c] == 0:
                    nxt.append(c)
        ready = sorted(nxt, key=steps.index)

    if len(order) != len(steps):
        cyclic = sorted([s for s in steps if s not in order], key=steps.index)
        return {"error": "cycle detected", "cyclic": cyclic,
                "ordered": order, "cloud_tokens": 0}

    return {"order": order, "waves": waves, "wave_count": len(waves),
            "max_parallel": max((len(w) for w in waves), default=0),
            "cloud_tokens": 0}
