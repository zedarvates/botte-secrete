#!/usr/bin/env python3
"""Log compressor — reduce large log files before agent ingestion.

Extracts unique patterns, counts repetitions, keeps representative samples.
Reduces token cost by ~80% for log analysis tasks.

    python -m skills.context_compressor.compress <logfile> [--max-lines 200]
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path


def compress(text: str, max_lines: int = 200) -> str:
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text

    # Count patterns (collapse numbers, timestamps, UUIDs)
    patterns = Counter()
    for line in lines:
        normalized = re.sub(r'\d+', 'N', line)
        normalized = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', 'UUID', normalized)
        normalized = re.sub(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}', 'TS', normalized)
        patterns[normalized] += 1

    # Build compressed output
    out = [f"# Log summary: {len(lines)} lines → {len(patterns)} unique patterns\n"]
    out.append(f"# Top patterns:\n")

    top = patterns.most_common(20)
    for pattern, count in top:
        out.append(f"  [{count}×] {pattern.strip()[:120]}\n")

    out.append(f"\n# Sample lines (first {min(50, max_lines)} unique):\n")
    seen = set()
    for line in lines:
        normalized = re.sub(r'\d+', 'N', line)
        if normalized not in seen:
            seen.add(normalized)
            out.append(line[:200] + "\n")
            if len(seen) >= 50:
                break

    return "".join(out)


if __name__ == "__main__":
    path = sys.argv[1]
    max_lines = int(sys.argv[2]) if len(sys.argv) > 2 else 200
    text = Path(path).read_text(errors="replace")
    result = compress(text, max_lines)
    print(result)
