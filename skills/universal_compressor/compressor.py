"""
Universal Compressor — Headroom-inspired multi-type compression.

Compresses text, JSON, logs, and tool output before they reach the LLM.
Reversible (CCR-like): can restore originals. Pure stdlib.

Strategies by content type:
    text     → collapse blank lines, summarize consecutive identical lines
    json     → remove whitespace outside strings; retain every value and key
    log      → summarize exact repetitions; retain distinct lines in order
    tool_out → strip ANSI colours; retain every line
    code     → unchanged (no verified language-aware transformation)

Usage:
    from skills.universal_compressor.compressor import compress
    result = compress(content, content_type="log")
    # → CompressedResult(data, original_size, compressed_size, ratio, reversible_key)
"""

from __future__ import annotations

import json
import re
import hashlib
from dataclasses import dataclass, field

# In-memory store for reversible compression
_REVERSIBLE_STORE: dict[str, str] = {}


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
    grounding_id: str = ""              # verified micro-NN oracle label, if recorded


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

    # Final flush: handle repeated lines at end of content
    if repeats >= 2:
        marker = f"[... {repeats} identical lines omitted ...]"
        if omitted_chars > len(marker):
            deduped.append(marker)
        else:
            for _ in range(repeats):
                deduped.append(deduped[-1] if deduped else "")

    elif repeats == 1:
        deduped.append(deduped[-1])

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
    """Minify valid JSON without sampling values or re-encoding number lexemes.

    max_array_items is retained for compatibility, but no longer drops items.
    """
    try:
        json.loads(content)
    except (ValueError, RecursionError):
        return CompressedResult(
            data=content, content_type="json",
            original_size=len(content), compressed_size=len(content),
            ratio=1.0, strategy="invalid_json_passthrough",
            warnings=["JSON could not be validated; original retained"],
        )

    # Match complete strings before whitespace so escaped quotes, spaces in
    # strings, duplicate keys and arbitrarily precise numeric lexemes survive.
    compressed = re.sub(
        r'"(?:\\.|[^"\\])*"|\s+',
        lambda match: match.group() if match.group().startswith('"') else "",
        content,
    )
    return CompressedResult(
        data=compressed, content_type="json",
        original_size=len(content), compressed_size=len(compressed),
        ratio=round(len(compressed) / max(len(content), 1), 3),
        strategy="json_whitespace_only",
    )

# ── Strategy: Log ─────────────────────────────────────────────

def _compress_log(content: str, max_lines: int = 50) -> CompressedResult:
    """Summarize exact repetitions, preserving distinct values and chronology.

    max_lines is a compression threshold, never a truncation budget.
    """
    if len(content.splitlines()) <= max_lines:
        return CompressedResult(
            data=content, content_type="log",
            original_size=len(content), compressed_size=len(content),
            ratio=1.0, strategy="no_compression_needed",
        )
    result = _compress_text(content)
    result.content_type = "log"
    result.strategy = "exact_repeats+collapse_blanks"
    return result

# ── Strategy: Tool Output ─────────────────────────────────────

def _compress_tool_output(content: str, max_length: int = 3000) -> CompressedResult:
    """Strip ANSI colours without hiding middle lines or truncating the tail.

    max_length is retained for compatibility; exceeding it cannot justify loss.
    """
    compressed = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', content)
    return CompressedResult(
        data=compressed, content_type="tool_output",
        original_size=len(content), compressed_size=len(compressed),
        ratio=round(len(compressed) / max(len(content), 1), 3),
        strategy="strip_ansi_only",
    )

# ── Strategy: Code ────────────────────────────────────────────

def _compress_code(content: str) -> CompressedResult:
    """Keep source exact until a language-aware transform is independently proven."""
    return CompressedResult(
        data=content, content_type="code",
        original_size=len(content), compressed_size=len(content),
        ratio=1.0, strategy="code_passthrough",
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
        if re.search(r'(error:|warning:|failed|passed|exit code)', line.lower()):
            return "tool_output"
    return "text"


# ── Main API ──────────────────────────────────────────────────

def compress(
    content: str,
    content_type: str = "auto",
    *,
    reversible: bool = False,
    learn: bool = False,
) -> CompressedResult:
    """Compress content using the best strategy for its type.

    Args:
        content: The content to compress
        content_type: "auto", "text", "json", "log", "tool_output", or "code"
        reversible: If True, store original for later restoration
        learn: Record a verified compression label after an exact roundtrip

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

    # Public sizes and ratio are measured UTF-8 bytes, not character/token estimates.
    result.original_size = len(content.encode("utf-8"))
    result.compressed_size = len(result.data.encode("utf-8"))
    result.ratio = round(result.compressed_size / max(result.original_size, 1), 3) if content else 1.0

    # Repeat markers can expand short input; retain the original in that case.
    if result.original_size > 0 and result.compressed_size > result.original_size:
        result = CompressedResult(
            data=content, content_type=result.content_type,
            original_size=result.original_size, compressed_size=result.original_size,
            ratio=1.0, strategy="none (would have expanded)",
            warnings=[*result.warnings, f"'{result.strategy}' expanded the input; passthrough used"],
        )

    if reversible:
        key = _make_reversible(result, content)
        result.reversible_key = key
        if learn and content:
            try:
                from skills.botte_nn.auto_labels import record_compression_result

                grounding_id = record_compression_result(
                    content, result.ratio, roundtrip_ok=(restore(key) == content)
                )
                result.grounding_id = grounding_id or ""
            except Exception:  # noqa: BLE001 - telemetry must never break compression
                pass

    return result


def _make_reversible(result: CompressedResult, original: str) -> str:
    """Store original content for later restoration."""
    key = hashlib.sha256(original.encode("utf-8")).hexdigest()
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
        "total_original_bytes": sum(len(v.encode("utf-8")) for v in _REVERSIBLE_STORE.values()),
    }
