"""Ultra-compact JSON — Single-char keys, delta-only patches, size comparison.

Three compression levels:
  1. Single-char keys (-30% vs compact JSON)
  2. Array format — no keys at all (-60%)
  3. Delta-only — send only what changed (-90% for iterative reports)
"""

import json
from typing import Any


# ── Key Mapping ──
KEY_MAP = {
    "h": "h", "s": "s", "g": "g",   # health, score, grade
    "st": "t", "f": "f", "l": "l",   # stats, files, lines
    "fn": "n",                        # findings
    "by": "b",                        # by_type
    "rc": "r", "p": "p", "d": "d",   # recommendations
    "ok": "o", "sk": "k", "fc": "c", # fix report
    "fx": "x", "uf": "u",
    "tk": "k", "b": "b", "a": "a", "pct": "p",  # tokens
    "ac": "a",
    "cat": "C", "saved": "s",
}

# Reverse map
REV_MAP = {v: k for k, v in KEY_MAP.items()}


def to_ultra(obj: dict) -> dict:
    """Convert standard compact JSON to single-char keys."""
    if isinstance(obj, dict):
        return {KEY_MAP.get(k, k): to_ultra(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [to_ultra(item) for item in obj]
    return obj


def from_ultra(obj: dict) -> dict:
    """Convert single-char keys back to standard compact JSON."""
    if isinstance(obj, dict):
        return {REV_MAP.get(k, k): from_ultra(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [from_ultra(item) for item in obj]
    return obj


def to_array(obj: dict) -> list:
    """Convert to array format — no keys, position-based.
    
    Audit report array: [health_score, health_grade, files, lines, [[file, sev, type, desc], ...]]
    Fix report array:   [fixed_count, skipped_count, files_changed, [fixes], [unfixed]]
    """
    if "h" in obj:
        # Audit report
        health = obj.get("h", {})
        stats = obj.get("t", obj.get("st", {}))
        findings = obj.get("n", obj.get("fn", []))
        return [
            health.get("s", 0),
            health.get("g", "F"),
            stats.get("f", 0),
            stats.get("l", 0),
            [[f.get("f",""), f.get("s","err"), f.get("t","dead"), f.get("d","")] for f in findings]
        ]
    elif "o" in obj or "ok" in obj:
        # Fix report
        fxs = obj.get("x", obj.get("fx", []))
        ufs = obj.get("u", obj.get("uf", []))
        return [
            obj.get("o", obj.get("ok", 0)),
            obj.get("k", obj.get("sk", 0)),
            obj.get("c", obj.get("fc", 0)),
            [[x.get("f",""), x.get("t","fix"), x.get("d","")] for x in fxs],
            [[u.get("f",""), u.get("t","skip"), u.get("d","")] for u in ufs],
        ]
    return []


def from_array(arr: list) -> dict:
    """Convert array format back to dict."""
    if len(arr) >= 5 and isinstance(arr[4], list):
        # Audit report
        findings = [{"f": f[0], "s": f[1], "t": f[2], "d": f[3]} for f in arr[4]]
        return {
            "h": {"s": arr[0], "g": arr[1]},
            "st": {"f": arr[2], "l": arr[3]},
            "fn": findings,
        }
    elif len(arr) >= 3 and isinstance(arr[0], int):
        # Fix report
        fxs = [{"f": x[0], "t": "fix", "d": x[2]} for x in arr[3]]
        ufs = [{"f": u[0], "t": "skip", "d": u[2]} for u in arr[4]]
        return {"ok": arr[0], "sk": arr[1], "fc": arr[2], "fx": fxs, "uf": ufs}
    return {}


def delta_only(prev: dict, curr: dict) -> dict:
    """Extract only what changed between two reports.
    
    For iterative pipelines (re-run audit after fix):
    - Only send NEW findings
    - Only send CHANGED stats
    - Everything else = same as before
    """
    delta = {}
    for key in set(list(prev.keys()) + list(curr.keys())):
        if key not in prev:
            delta[key] = curr[key]
        elif key not in curr:
            delta[key] = None  # removed
        elif key == "fn" or key == "n":
            # Compare findings
            prev_ids = {f.get("f","") + f.get("d","") for f in prev.get(key, [])}
            curr_items = curr.get(key, [])
            new_findings = [f for f in curr_items if (f.get("f","") + f.get("d","")) not in prev_ids]
            if new_findings:
                delta[key] = new_findings
        elif prev[key] != curr[key]:
            delta[key] = curr[key]
    return delta


def compare_sizes(obj: dict) -> dict:
    """Compare all formats and return savings metrics."""
    compact = json.dumps(obj)
    ultra = json.dumps(to_ultra(obj))
    arr = json.dumps(to_array(obj))

    return {
        "compact": len(compact),
        "ultra": len(ultra),
        "ultra_savings_pct": round((1 - len(ultra)/len(compact)) * 100, 1),
        "array": len(arr),
        "array_savings_pct": round((1 - len(arr)/len(compact)) * 100, 1),
    }


# ── Demo ──
if __name__ == "__main__":
    report = {
        "h": {"s": 59, "g": "C"},
        "st": {"f": 40, "l": 3841},
        "fn": [
            {"f": "core.py:42", "s": "err", "t": "dead", "d": "calc_tax()"},
            {"f": "auth.py:30", "s": "crit", "t": "sec", "d": "API_KEY in log"},
            {"f": "utils.py:88", "s": "warn", "t": "dup", "d": "parse_input() x3"},
        ],
    }

    cmp = compare_sizes(report)
    print("=== Ultra-Compact JSON ===")
    print(f"Compact:          {cmp['compact']} chars")
    print(f"Ultra (1-char):   {cmp['ultra']} chars (-{cmp['ultra_savings_pct']}%)")
    print(f"Array (no keys):  {cmp['array']} chars (-{cmp['array_savings_pct']}%)")

    # Delta test
    report2 = {
        "h": {"s": 72, "g": "B"},
        "st": {"f": 42, "l": 3900},
        "fn": [
            {"f": "core.py:42", "s": "err", "t": "dead", "d": "calc_tax()"},  # same
            {"f": "auth.py:30", "s": "info", "t": "sec", "d": "API_KEY fixed"},  # changed
            {"f": "new.py:15", "s": "err", "t": "dead", "d": "new_dead()"},  # new
        ],
    }
    delta = delta_only(report, report2)
    delta_ultra = json.dumps(to_ultra(delta))
    print(f"\\nDelta-only:        {len(delta_ultra)} chars")
    print(f"  (full report would be {cmp['compact']} chars)")
    print(f"  Savings: -{round((1 - len(delta_ultra)/cmp['compact'])*100)}%")
