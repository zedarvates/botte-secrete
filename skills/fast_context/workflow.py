"""Explicit local discovery/context workflow; no automatic retry or execution."""
from __future__ import annotations

from skills.fast_context.symbols import locate_symbol_file, read_symbol_context_file


def prepare_code_context(filepath: str, name: str, *, expected_sha256: str | None = None,
                         occurrence: int | None = None, before: int = 3, after: int = 30,
                         max_context_bytes: int = 16384) -> dict:
    """Use an explicit historical reference or discover a fresh one first.

    A fresh reference is a current observation, not historical evidence or
    proof that this is the revision intended by the caller. A second bounded
    read detects changes since discovery. Stale results are never retried.
    """
    if expected_sha256 is None:
        discovery = locate_symbol_file(filepath, name, max_results=20)
        reference = discovery['source_sha256']
        origin = 'fresh_discovery'
    else:
        reference = expected_sha256
        origin = 'caller_expected'
    context = read_symbol_context_file(filepath, name, reference, occurrence=occurrence,
                                       before=before, after=after,
                                       max_context_bytes=max_context_bytes)
    return {'schema': 'botte.code-context-bundle/v1', 'status': context['status'],
            'reference_origin': origin, 'reference_sha256': reference, 'context': context}
