"""Bounded lexical declaration lookup for explicit Zig/GDScript files.

This is a locator, not a parser, type checker or full function-body extractor.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import stat

MAX_SOURCE_BYTES = 1_048_576
MAX_SNIPPET_BYTES = 1024
LANGUAGES = {'.zig': 'zig', '.gd': 'gdscript'}
_DECLARATIONS = {
    'zig': re.compile(r'^\s*(?:(?:pub|export|extern|inline|noinline)\s+)*fn\s+([A-Za-z_][A-Za-z0-9_]*)\s*\('),
    'gdscript': re.compile(r'^\s*(?:static\s+)?func\s+([A-Za-z_][A-Za-z0-9_]*)\s*\('),
}


def _code_lines(source: str, language: str) -> list[str]:
    """Mask quoted text/comments without changing line or column positions."""
    lines, quote = [], ''
    for original in source.split('\n'):
        masked = list(original)
        if language == 'zig' and not quote and original.lstrip().startswith('\\\\'):
            lines.append(''.join(' ' if c not in '\r\n' else c for c in original))
            continue
        i = 0
        while i < len(original):
            char = original[i]
            if quote:
                width = 1
                if original.startswith(quote, i):
                    width, quote = len(quote), ''
                elif char == '\\':
                    width = min(2, len(original) - i)
                for j in range(i, i + width):
                    if masked[j] not in '\r\n':
                        masked[j] = ' '
                i += width
                continue
            if ((language == 'zig' and original.startswith('//', i))
                    or (language == 'gdscript' and char == '#')):
                for j in range(i, len(original)):
                    if masked[j] not in '\r\n':
                        masked[j] = ' '
                break
            if char in ('"', "'"):
                width = 3 if language == 'gdscript' and original.startswith(char * 3, i) else 1
                quote = char * width
                for j in range(i, i + width):
                    masked[j] = ' '
                i += width
                continue
            i += 1
        lines.append(''.join(masked))
    if lines and lines[0].startswith('\ufeff'):
        lines[0] = ' ' + lines[0][1:]
    return lines


def locate_symbol(source: str, language: str, name: str, max_results: int = 10) -> dict:
    if not isinstance(source, str):
        raise ValueError('source must be UTF-8 text')
    raw = source.encode('utf-8')
    if len(raw) > MAX_SOURCE_BYTES or '\x00' in source:
        raise ValueError('source must be NUL-free and at most 1 MiB')
    if not isinstance(language, str) or language not in _DECLARATIONS:
        raise ValueError('language must be zig or gdscript')
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,127}', name):
        raise ValueError('name must be an ASCII identifier of at most 128 characters')
    if isinstance(max_results, bool) or not isinstance(max_results, int) or not 1 <= max_results <= 20:
        raise ValueError('max_results must be an integer from 1 through 20')
    originals = source.split('\n')
    results, total = [], 0
    for number, line in enumerate(_code_lines(source, language), 1):
        match = _DECLARATIONS[language].match(line)
        if not match or match.group(1) != name:
            continue
        total += 1
        if len(results) < max_results:
            text = originals[number - 1].strip().encode('utf-8')
            results.append({'line': number, 'column': match.start(1) + 1,
                            'snippet': text[:MAX_SNIPPET_BYTES].decode('utf-8', errors='ignore'),
                            'snippet_truncated': len(text) > MAX_SNIPPET_BYTES})
    return {'schema': 'botte.code-symbol-locations/v1', 'language': language, 'name': name,
            'source_sha256': hashlib.sha256(raw).hexdigest(), 'source_bytes': len(raw),
            'syntax_checked': False, 'body_included': False,
            'results': results, 'total_candidates': total, 'omitted_candidates': total - len(results)}


def _read_source_file(filepath: str) -> tuple[Path, str, bytes]:
    """One bounded snapshot; leaf symlinks/non-regular files are refused.

    This is not an OS sandbox or a repository allowlist. Parent path selection
    and user authorization remain the caller's responsibility.
    """
    path = Path(filepath)
    language = LANGUAGES.get(path.suffix.lower())
    if language is None:
        raise ValueError('file extension must be .zig or .gd')
    if path.is_symlink():
        raise ValueError('leaf symlinks are not supported')
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError('source must be a regular file')
        raw = stream.read(MAX_SOURCE_BYTES + 1)
    if len(raw) > MAX_SOURCE_BYTES:
        raise ValueError('source exceeds 1 MiB')
    return path, language, raw


def locate_symbol_file(filepath: str, name: str, max_results: int = 10) -> dict:
    path, language, raw = _read_source_file(filepath)
    report = locate_symbol(raw.decode('utf-8'), language, name, max_results)
    report['file'] = str(path)
    return report


def read_symbol_context_file(filepath: str, name: str, expected_sha256: str, *,
                             occurrence: int | None = None, before: int = 3,
                             after: int = 30, max_context_bytes: int = 16384) -> dict:
    """Return an exact line window from the same bytes as the checked digest.

    Whole lines only, declaration first, then following lines, then preceding
    lines. A window can cross another declaration and is not a complete body.
    """
    if not isinstance(expected_sha256, str) or not re.fullmatch(r'[0-9a-f]{64}', expected_sha256):
        raise ValueError('expected_sha256 must be 64 lowercase hexadecimal characters')
    for value, label, low, high in ((before, 'before', 0, 20), (after, 'after', 0, 100),
                                    (max_context_bytes, 'max_context_bytes', 256, 65536)):
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError(f'{label} must be an integer from {low} through {high}')
    if occurrence is not None and (isinstance(occurrence, bool) or not isinstance(occurrence, int)
                                   or not 1 <= occurrence <= 20):
        raise ValueError('occurrence must be an integer from 1 through 20')
    # Validate the symbol before any file access.
    locate_symbol('', 'zig', name, 1)
    path, language, raw = _read_source_file(filepath)
    digest = hashlib.sha256(raw).hexdigest()
    report = {'schema': 'botte.code-symbol-context/v1', 'file': str(path),
              'language': language, 'name': name, 'expected_sha256': expected_sha256,
              'source_sha256': digest, 'source_bytes': len(raw), 'syntax_checked': False,
              'function_body_complete': None, 'text': '', 'context_bytes': 0}
    if digest != expected_sha256:
        return {**report, 'status': 'stale_source'}
    source = raw.decode('utf-8')
    locations = locate_symbol(source, language, name, 20)
    count = locations['total_candidates']
    report['total_candidates'] = count
    if count == 0 or (occurrence is not None and occurrence > count):
        return {**report, 'status': 'not_found'}
    if count > 1 and occurrence is None:
        return {**report, 'status': 'ambiguous',
                'candidate_lines': [r['line'] for r in locations['results']],
                'omitted_candidates': locations['omitted_candidates']}
    chosen = locations['results'][(occurrence or 1) - 1]
    parts = source.split('\n')
    lines = [part + '\n' for part in parts[:-1]] + ([parts[-1]] if parts[-1] else [])
    anchor = chosen['line'] - 1
    used = len(lines[anchor].encode('utf-8'))
    report['declaration_line'] = anchor + 1
    report['occurrence'] = occurrence or 1
    if used > max_context_bytes:
        return {**report, 'status': 'context_over_budget', 'required_declaration_bytes': used}
    requested_start, requested_end = max(0, anchor - before), min(len(lines) - 1, anchor + after)
    start = end = anchor
    while end < requested_end:
        size = len(lines[end + 1].encode('utf-8'))
        if used + size > max_context_bytes:
            break
        used += size
        end += 1
    while start > requested_start:
        size = len(lines[start - 1].encode('utf-8'))
        if used + size > max_context_bytes:
            break
        used += size
        start -= 1
    text = ''.join(lines[start:end + 1])
    return {**report, 'status': 'completed', 'text': text, 'context_bytes': used,
            'context_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
            'start_line': start + 1, 'end_line': end + 1,
            'omitted_before_lines': start - requested_start,
            'omitted_after_lines': requested_end - end,
            'window_complete': start == requested_start and end == requested_end}
