"""Agent-Native Diff Language — Ultra-compact code change descriptions.

Format: {op}:{file}:{lines}:{symbol}:{detail}

Operations:
    +f = fix applied
    -f = fix skipped
    +d = dead code found
    -d = dead code (false positive)
    +c = complexity issue
    +p = duplication
    +s = secret found
    +b = boundary violation
    +g = feature flag

Severity (prefix):
    !! = critical
    !  = error
    ~  = warning
    .  = info

Examples:
    +f:core.py:42::calc_tax::CMT::grep→0  → Fix: commented dead code, verified
    -f:utils.py:88::parse::SKP::getattr   → Skip: called dynamically
    !!:auth.py:30::key::secret::log_exposed → Critical: secret in log
    +d:api.py:142::handler::0refs         → Dead code: 0 references
    +g:config.py:15::FEATURE_X::stale     → Feature flag: stale

For bulk changes, separate multiple symbols with commas:
    +f:core.py:42,88,120::calc_tax,parse,validate::CMT → 3 fixes in same file
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Op(str, Enum):
    FIX = "+f"
    SKIP = "-f"
    DEAD = "+d"
    DEAD_FP = "-d"      # false positive
    COMPLEX = "+c"
    DUP = "+p"
    SECRET = "+s"
    BOUNDARY = "+b"
    FLAG = "+g"


class Sev(str, Enum):
    CRIT = "!!"
    ERR = "!"
    WARN = "~"
    INFO = "."


@dataclass
class DiffLine:
    """A single diff entry in compact format."""
    op: Op
    file: str
    lines: str            # "42" or "42,88,120"
    symbol: str           # function/class name
    detail: str           # CMT, SKP, grep→0, etc.
    sev: Sev = Sev.ERR

    def to_compact(self) -> str:
        """Serialize to compact string."""
        return f"{self.sev.value}{self.op.value}:{self.file}:{self.lines}:{self.symbol}:{self.detail}"

    @classmethod
    def from_compact(cls, s: str) -> DiffLine:
        """Parse from compact string."""
        # Extract severity prefix
        if s.startswith("!!"):
            sev, rest = Sev.CRIT, s[2:]
        elif s.startswith("!"):
            sev, rest = Sev.ERR, s[1:]
        elif s.startswith("~"):
            sev, rest = Sev.WARN, s[1:]
        elif s.startswith("."):
            sev, rest = Sev.INFO, s[1:]
        else:
            sev, rest = Sev.ERR, s

        op_str, rest = rest.split(":", 1)
        file, rest = rest.split(":", 1)
        lines, rest = rest.split(":", 1)
        symbol, detail = rest.split(":", 1)

        return cls(op=Op(op_str), file=file, lines=lines, symbol=symbol, detail=detail, sev=sev)

    def to_verbose(self) -> str:
        """Convert to verbose markdown (for human reading)."""
        op_verbose = {
            Op.FIX: "Fixed",
            Op.SKIP: "Skipped",
            Op.DEAD: "Dead code",
            Op.DEAD_FP: "Dead code (false +)",
            Op.COMPLEX: "Complexity",
            Op.DUP: "Duplication",
            Op.SECRET: "Secret",
            Op.BOUNDARY: "Boundary",
            Op.FLAG: "Feature flag",
        }
        sev_verbose = {
            Sev.CRIT: "🔴 CRITICAL",
            Sev.ERR: "🟠 ERROR",
            Sev.WARN: "🟡 WARNING",
            Sev.INFO: "ℹ️ INFO",
        }
        return f"`{self.file}:{self.lines}` — {op_verbose.get(self.op, '?')}: `{self.symbol}` ({self.detail}) [{sev_verbose.get(self.sev, '?')}]"


class DiffReport:
    """A complete diff report in compact format."""

    def __init__(self):
        self.entries: list[DiffLine] = []

    def add(self, entry: DiffLine):
        self.entries.append(entry)

    def to_compact(self) -> str:
        """All entries as compact lines."""
        return "\n".join(e.to_compact() for e in self.entries)

    @classmethod
    def from_compact(cls, text: str) -> DiffReport:
        """Parse from compact format."""
        report = cls()
        for line in text.strip().split("\n"):
            if line.strip():
                report.add(DiffLine.from_compact(line.strip()))
        return report

    def to_verbose(self) -> str:
        """Convert to verbose markdown report."""
        lines = ["# 📋 Diff Report", f"Entries: {len(self.entries)}", ""]
        by_sev = {}
        for e in self.entries:
            by_sev.setdefault(e.sev, []).append(e)

        for sev in [Sev.CRIT, Sev.ERR, Sev.WARN, Sev.INFO]:
            entries = by_sev.get(sev, [])
            if entries:
                lines.append(f"## {sev.value} ({len(entries)})")
                for e in entries:
                    lines.append(f"- {e.to_verbose()}")
                lines.append("")

        return "\n".join(lines)

    def stats(self) -> dict:
        """Summary statistics."""
        by_op = {}
        by_sev = {}
        for e in self.entries:
            by_op[e.op.value] = by_op.get(e.op.value, 0) + 1
            by_sev[e.sev.value] = by_sev.get(e.sev.value, 0) + 1
        return {"total": len(self.entries), "by_op": by_op, "by_sev": by_sev}

    def compact_size(self) -> int:
        """Size in chars of compact representation."""
        return len(self.to_compact())

    def verbose_size(self) -> int:
        """Size in chars of verbose representation."""
        return len(self.to_verbose())

    def savings(self) -> float:
        """Token savings: (verbose - compact) / verbose * 100."""
        v = self.verbose_size()
        c = self.compact_size()
        if v == 0:
            return 0.0
        return round((v - c) / v * 100, 1)


# ── Demo ──

if __name__ == "__main__":
    # Simulate a d'Artagnan fix report
    report = DiffReport()
    report.add(DiffLine(Op.FIX, "core.py", "42", "calc_tax", "CMT::grep→0", Sev.ERR))
    report.add(DiffLine(Op.FIX, "cli.py", "26", "dead_handler", "CMT::node--check→OK", Sev.ERR))
    report.add(DiffLine(Op.SKIP, "utils.py", "88", "parse_input", "SKP::getattr", Sev.WARN))
    report.add(DiffLine(Op.SECRET, "auth.py", "30", "API_KEY", "log_exposed", Sev.CRIT))
    report.add(DiffLine(Op.DEAD, "old_mod.py", "15,42,88", "legacy_fn1,legacy_fn2,legacy_fn3", "0refs", Sev.ERR))

    print("=== Compact Format ===")
    print(report.to_compact())
    print(f"\nCompact size: {report.compact_size()} chars (~{report.compact_size()//4} tok)")

    print("\n=== Verbose Format ===")
    verbose = report.to_verbose()
    print(verbose[:500] + "...")
    print(f"Verbose size: {report.verbose_size()} chars (~{report.verbose_size()//4} tok)")

    print(f"\n💰 Savings: {report.savings()}%")
    print(f"Stats: {report.stats()}")

    # Roundtrip test
    print("\n=== Roundtrip Test ===")
    compact = report.to_compact()
    parsed = DiffReport.from_compact(compact)
    print(f"Original: {len(report.entries)} entries")
    print(f"Parsed:   {len(parsed.entries)} entries")
    print(f"Match: {report.to_compact() == parsed.to_compact()}")
