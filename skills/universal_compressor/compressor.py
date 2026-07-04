"""
Universal Compressor — Headroom-inspired multi-type compression.

Compresses text, JSON, logs, and tool output before they reach the LLM.
Reversible (CCR-like): can restore originals. Pure stdlib.

Strategies by content type:
    text     → strip whitespace, dedup lines, truncate repetitions
    json     → compact (no spaces), array→summary, truncate large objects
    log      → dedup patterns, count occurrences, sample representative lines
    tool_out → truncate long outputs, strip ANSI, keep first/last N lines
    code     → strip comments, collapse imports, summarize structure

Usage:
    from skills.universal_compressor.compressor import compress
    result = compress(content, content_type="log")
    # → CompressedResult(data, original_size, compressed_size, ratio, reversible_key)
"""

from __future__ import annotations

import json
import re
import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# In-memory store for reversible compression
_REVERSIBLE_STORE: dict[str, str] = {}
_STORE_PATH = Path.home() / ".botte" / "compressor-store.json"


@dataclass(slots=True)
class CompressedResult:
    """Result of compressing content."""
    data: str                          # the compressed content
    content_type: str                  # detected/requested type
    original_size: int                 # bytes before
    compressed_size: int               # bytes after
    ratio: float                       # compression ratio (0-1)
    reversible_key: str = ""           # key to restore original (empty if irreversible)
    strategy: str = ""                 # which strategy was used
    warnings: list[str] = field(default_factory=list)


# ── Strategy: Text ────────────────────────────────────────────

def _compress_text(content: str) -> CompressedResult:
    """Compress general text: strip extra whitespace, dedup repeated lines."""
    original = content
    lines = content.splitlines()

    # Dedup consecutive repeated lines (keep first, note count)
    # Only compress if the compression marker is shorter than the omitted content
    deduped: list[str] = []
    repeats = 0
    omitted_chars = 0
    for line in lines:
        if deduped and deduped[-1] == line and line.strip():
            repeats += 1
            omitted_chars += len(line) + 1  # +1 for newline
            continue
        if repeats >= 2:  # at least 3 identical lines
            marker = f"[... {repeats} identical lines omitted ...]"
            if omitted_chars > len(marker):  # only if we actually save space
                deduped.append(marker)
            else:
                # Not worth it — put the lines back
                for _ in range(repeats):
                    deduped.append(deduped[-1])
            repeats = 0
            omitted_chars = 0
        elif repeats > 0:
            for _ in range(repeats):
                deduped.append(deduped[-1])
            repeats = 0
            omitted_chars = 0
        deduped.append(line)

    # Collapse multiple blank lines
    result = []
    blank_count = 0
    for line in deduped:
        if not line.strip():
            blank_count += 1
            if blank_count <= 1:
                result.append(line)
        else:
            blank_count = 0
            result.append(line)

    compressed = "\n".join(result)
    return CompressedResult(
        data=compressed,
        content_type="text",
        original_size=len(original),
        compressed_size=len(compressed),
        ratio=round(len(compressed) / max(len(original), 1), 3),
        strategy="dedup_lines+collapse_blanks",
    )


# ── Strategy: JSON ────────────────────────────────────────────

def _compress_json(content: str, max_array_items: int = 5) -> CompressedResult:
    """Compress JSON: compact format, summarize large arrays."""
    original = content
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        # Not valid JSON, fall back to text compression
        return _compress_text(content)

    def _compact(obj, depth=0):
        if depth > 4:
            return "..."
        if isinstance(obj, dict):
            if len(obj) > 10:
                keys = list(obj.keys())
                summary = {k: _compact(obj[k], depth + 1) for k in keys[:5]}
                summary["..."] = f"{len(obj) - 5} more keys"
                return summary
            return {k: _compact(v, depth + 1) for k, v in obj.items()}
        if isinstance(obj, list):
            if len(obj) > max_array_items:
                return [_compact(x, depth + 1) for x in obj[:3]] + [f"... ({len(obj) - 3} more items)"]
            return [_compact(x, depth + 1) for x in obj]
        if isinstance(obj, str) and len(obj) > 200:
            return obj[:200] + "..."
        return obj

    compacted = _compact(data)
    compressed = json.dumps(compacted, ensure_ascii=False, separators=(",", ":"))
    return CompressedResult(
        data=compressed,
        content_type="json",
        original_size=len(original),
        compressed_size=len(compressed),
        ratio=round(len(compressed) / max(len(original), 1), 3),
        strategy="compact+truncate_arrays",
    )


# ── Strategy: Log ─────────────────────────────────────────────

def _compress_log(content: str, max_lines: int = 50) -> CompressedResult:
    """Compress logs: dedup patterns, sample representative lines."""
    original = content
    lines = [l.rstrip() for l in content.splitlines() if l.strip()]

    if len(lines) <= max_lines:
        return CompressedResult(
            data=content, content_type="log",
            original_size=len(original), compressed_size=len(original),
            ratio=1.0, strategy="no_compression_needed",
        )

    # Count patterns (strip timestamps/numbers for grouping)
    pattern_counts: dict[str, list[str]] = {}
    for line in lines:
        normalized = re.sub(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}', '<TS>', line)
        normalized = re.sub(r'\d+', '<N>', normalized)
        pattern_counts.setdefault(normalized, []).append(line)

    # Build summary: first occurrence + count + last occurrence
    result_lines: list[str] = []
    result_lines.append(f"[Log summary: {len(lines)} lines → {len(pattern_counts)} unique patterns]")
    for pattern, occurrences in sorted(pattern_counts.items(), key=lambda x: -len(x[1])):
        if len(occurrences) == 1:
            result_lines.append(occurrences[0][:120])
        else:
            result_lines.append(f"[{len(occurrences)}×] {occurrences[0][:120]}")
        if len(result_lines) > max_lines:
            result_lines.append(f"... ({len(pattern_counts) - len(result_lines) + 1} more patterns)")
            break

    compressed = "\n".join(result_lines)
    return CompressedResult(
        data=compressed,
        content_type="log",
        original_size=len(original),
        compressed_size=len(compressed),
        ratio=round(len(compressed) / max(len(original), 1), 3),
        strategy="pattern_dedup+sampling",
    )


# ── Strategy: Tool Output ─────────────────────────────────────

def _compress_tool_output(content: str, max_length: int = 3000) -> CompressedResult:
    """Compress CLI tool output: keep head+tail, strip ANSI, truncate middle."""
    original = content

    # Strip ANSI escape codes
    ansi_free = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', content)
    lines = ansi_free.splitlines()

    if len(ansi_free) <= max_length:
        return CompressedResult(
            data=ansi_free, content_type="tool_output",
            original_size=len(original), compressed_size=len(ansi_free),
            ratio=1.0, strategy="strip_ansi_only",
        )

    # Keep head and tail
    head_lines = 20
    tail_lines = 10
    if len(lines) <= head_lines + tail_lines + 2:
        return CompressedResult(
            data=ansi_free, content_type="tool_output",
            original_size=len(original), compressed_size=len(ansi_free),
            ratio=1.0, strategy="no_truncation_needed",
        )

    head = lines[:head_lines]
    tail = lines[-tail_lines:]
    omitted = len(lines) - head_lines - tail_lines
    result_lines = (
        head
        + [f"\n... [{omitted} lines omitted, {len(ansi_free)} → {max_length} chars] ...\n"]
        + tail
    )
    compressed = "\n".join(result_lines)[:max_length]
    compressed += f"\n[truncated at {max_length} chars, original: {len(original)} bytes]"

    return CompressedResult(
        data=compressed,
        content_type="tool_output",
        original_size=len(original),
        compressed_size=len(compressed),
        ratio=round(len(compressed) / max(len(original), 1), 3),
        strategy="head_tail+ansi_strip",
    )


# ── Strategy: Code ────────────────────────────────────────────

def _compress_code(content: str) -> CompressedResult:
    """Compress code: strip comments, collapse imports, summarize structure."""
    original = content
    lines = content.splitlines()
    result_lines: list[str] = []
    import_count = 0

    for line in lines:
        stripped = line.strip()
        # Collapse consecutive imports
        if stripped.startswith(("import ", "from ")):
            import_count += 1
            continue
        if import_count > 0:
            result_lines.append(f"# [{import_count} import lines]")
            import_count = 0
        # Strip inline comments (but not docstrings)
        if "#" in line and not stripped.startswith(('"""', "'''")):
            code_part = line.split("#")[0].rstrip()
            if code_part.strip():
                result_lines.append(code_part)
        else:
            result_lines.append(line)

    if import_count > 0:
        result_lines.append(f"# [{import_count} import lines]")

    compressed = "\n".join(result_lines)
    return CompressedResult(
        data=compressed,
        content_type="code",
        original_size=len(original),
        compressed_size=len(compressed),
        ratio=round(len(compressed) / max(len(original), 1), 3),
        strategy="strip_comments+collapse_imports",
    )


# ── Strategy: Auto-detect ─────────────────────────────────────

def _detect_type(content: str) -> str:
    """Auto-detect content type."""
    if not content.strip():
        return "text"
    # Try JSON
    try:
        json.loads(content)
        return "json"
    except json.JSONDecodeError:
        pass
    # Check for log patterns (timestamps, log levels)
    log_indicators = 0
    lines_sample = content.splitlines()[:20]
    for line in lines_sample:
        if re.search(r'(ERROR|WARN|INFO|DEBUG|TRACE)\s', line):
            log_indicators += 1
        if re.search(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}', line):
            log_indicators += 1
    if log_indicators >= 2:
        return "log"
    # Check for code (lots of symbols, indentation)
    code_indicators = 0
    for line in lines_sample:
        if re.search(r'(def |class |import |from |\{|\(|\))', line):
            code_indicators += 1
        if line.startswith((" ", "\t")):
            code_indicators += 1
    if code_indicators >= 3:
        return "code"
    # Check for tool output patterns (paths, commands, exit codes)
    for line in lines_sample:
        if re.search(r'(error:|warning:|FAILED|PASSED|exit code)', line.lower()):
            return "tool_output"
    return "text"


# ── Main API ──────────────────────────────────────────────────

def compress(
    content: str,
    content_type: str = "auto",
    *,
    reversible: bool = False,
) -> CompressedResult:
    """Compress content using the best strategy for its type.

    Args:
        content: The content to compress
        content_type: "auto", "text", "json", "log", "tool_output", or "code"
        reversible: If True, store original for later restoration

    Returns:
        CompressedResult with compressed data and metrics
    """
    if content_type == "auto":
        content_type = _detect_type(content)

    strategies = {
        "text": _compress_text,
        "json": _compress_json,
        "log": _compress_log,
        "tool_output": _compress_tool_output,
        "code": _compress_code,
    }

    compressor = strategies.get(content_type, _compress_text)
    result = compressor(content)

    if reversible:
        key = _make_reversible(result, content)
        result.reversible_key = key

    return result


def _make_reversible(result: CompressedResult, original: str) -> str:
    """Store original content for later restoration."""
    key = hashlib.sha256(original.encode()[:256]).hexdigest()[:12]
    _REVERSIBLE_STORE[key] = original
    return key


def restore(key: str) -> str | None:
    """Restore original content from a reversible key."""
    return _REVERSIBLE_STORE.get(key)


def flush_store():
    """Clear the reversible store."""
    _REVERSIBLE_STORE.clear()


def stats() -> dict:
    """Return compression store statistics."""
    return {
        "stored_originals": len(_REVERSIBLE_STORE),
        "total_original_bytes": sum(len(v) for v in _REVERSIBLE_STORE.values()),
    }
