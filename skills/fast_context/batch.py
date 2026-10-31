"""Explicit root-scoped context batches; no recursive discovery or model call."""
from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
import re
import stat

from skills.fast_context.workflow import prepare_code_context


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def read_batch_request(filepath: str) -> dict:
    path = Path(filepath)
    if path.is_symlink():
        raise ValueError('request leaf symlinks are not supported')
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    with os.fdopen(os.open(path, flags), 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError('request must be a regular file')
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ValueError('request exceeds 64 KiB')
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
    except RecursionError as error:
        raise ValueError('request nesting is too deep') from error


def _validated_items(request: dict, root: Path) -> list[tuple[dict, Path]]:
    if (not isinstance(request, dict) or set(request) != {'schema', 'items'}
            or request['schema'] != 'botte.code-context-request/v1'):
        raise ValueError('expected botte.code-context-request/v1 with schema/items only')
    items = request['items']
    if not isinstance(items, list) or not 1 <= len(items) <= 16:
        raise ValueError('items must contain 1 through 16 entries')
    validated, ids = [], set()
    allowed = {'id', 'file', 'name', 'expected_sha256', 'occurrence', 'before', 'after'}
    for item in items:
        if not isinstance(item, dict) or not {'id', 'file', 'name'} <= set(item) or set(item) - allowed:
            raise ValueError('invalid item fields')
        identifier = item['id']
        if not isinstance(identifier, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', identifier) or identifier in ids:
            raise ValueError('item IDs must be unique bounded identifiers')
        ids.add(identifier)
        file = item['file']
        if (not isinstance(file, str) or not file or len(file.encode('utf-8')) > 512
                or '\\' in file or ':' in file or any(ord(c) < 32 for c in file)):
            raise ValueError('file must be a bounded relative POSIX path')
        relative = PurePosixPath(file)
        if relative.is_absolute() or '..' in relative.parts or relative.suffix.lower() not in {'.zig', '.gd'}:
            raise ValueError('file must be an in-project .zig/.gd path without parent traversal')
        candidate = root.joinpath(*relative.parts)
        for parent in (candidate, *candidate.parents):
            if parent == root:
                break
            if parent.is_symlink():
                raise ValueError('source symlinks are not supported in batches')
        try:
            candidate.resolve().relative_to(root)
        except ValueError as error:
            raise ValueError('source escapes the selected project root') from error
        if not isinstance(item['name'], str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,127}', item['name']):
            raise ValueError('invalid function name')
        if 'expected_sha256' in item and (not isinstance(item['expected_sha256'], str)
                or not re.fullmatch(r'[0-9a-f]{64}', item['expected_sha256'])):
            raise ValueError('invalid expected_sha256')
        for key, low, high in (('occurrence', 1, 20), ('before', 0, 20), ('after', 0, 100)):
            if key in item and (type(item[key]) is not int or not low <= item[key] <= high):
                raise ValueError(f'invalid {key}')
        validated.append((dict(item), candidate))
    return validated


def prepare_code_batch(request: dict, root: str, *, max_context_bytes: int = 32768) -> dict:
    if type(max_context_bytes) is not int or not 256 <= max_context_bytes <= 131072:
        raise ValueError('max_context_bytes must be an integer from 256 through 131072')
    project = Path(root).resolve()
    if not project.is_dir():
        raise ValueError('root must be an existing project directory')
    # Reject malformed/out-of-scope entries before opening any source file.
    validated = _validated_items(request, project)
    used, completed, limited = 0, 0, 0
    rows, observed = [], {}
    for item, path in validated:
        row = {'id': item['id'], 'file': item['file'], 'name': item['name']}
        remaining = max_context_bytes - used
        if remaining < 256:
            rows.append({**row, 'status': 'budget_exhausted'})
            continue
        kwargs = {key: item[key] for key in ('expected_sha256', 'occurrence', 'before', 'after') if key in item}
        try:
            bundle = prepare_code_context(str(path), item['name'],
                                          max_context_bytes=min(remaining, 65536), **kwargs)
        except (OSError, ValueError) as error:
            rows.append({**row, 'status': 'read_error', 'error': str(error)[:256]})
            continue
        context = bundle['context']
        key = str(path)
        if bundle['status'] == 'completed':
            digest = context['source_sha256']
            if key in observed and observed[key] != digest:
                rows.append({**row, 'status': 'source_changed_between_items',
                             'first_source_sha256': observed[key], 'observed_source_sha256': digest})
                continue
            observed[key] = digest
            used += context['context_bytes']
            completed += 1
            limited += not context['window_complete']
        rows.append({**row, 'status': bundle['status'], 'bundle': bundle})
    return {'schema': 'botte.code-context-batch/v1',
            'status': 'completed' if completed == len(rows) and limited == 0 else 'incomplete',
            'items': rows, 'items_requested': len(rows), 'items_completed': completed,
            'limited_windows': limited, 'context_bytes': used, 'context_budget_bytes': max_context_bytes,
            'atomic_project_snapshot': False}
