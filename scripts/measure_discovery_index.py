#!/usr/bin/env python3
"""Measure authored discovery exchanges through the actual local stdio server.

Run from the checkout: python scripts/measure_discovery_index.py > report.json
No model/backend/tool execution; results measure serialized bytes only.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from skills.llm_mcp.lazy import find_tool
from skills.llm_mcp.server import TOOLS


def main() -> int:
    queries = ('memory', 'route', 'verify', 'security', 'compress', 'docs')
    requests, cases = [], []

    def request(arguments: dict) -> int:
        identifier = len(requests) + 1
        requests.append({'jsonrpc': '2.0', 'id': identifier, 'method': 'tools/call',
                         'params': {'name': 'find_tool', 'arguments': arguments}})
        return identifier - 1

    for query in queries:
        matches = find_tool(query, TOOLS)['matches']
        selected = matches[0]['name']  # Authored policy, not a quality judgment.
        baseline = [request({'query': query})]
        if 'inputSchema' not in matches[0]:
            baseline.append(request({'query': selected, 'top_k': 1, 'schema_budget_bytes': 65536}))
        candidate = [request({'query': query, 'detail': 'index'}),
                     request({'query': selected, 'top_k': 1, 'schema_budget_bytes': 65536})]
        cases.append((query, selected, baseline, candidate))

    lines = [json.dumps(item, ensure_ascii=False) + '\n' for item in requests]
    process = subprocess.run([sys.executable, '-m', 'skills.llm_mcp.server'],
                             input=''.join(lines).encode('utf-8'), capture_output=True, cwd=ROOT, timeout=30, check=True)
    responses = process.stdout.splitlines(keepends=True)
    if len(responses) != len(lines):
        raise RuntimeError('incomplete stdio responses')
    payloads = []
    for req, response in zip(requests, responses):
        parsed = json.loads(response)
        if parsed.get('id') != req['id'] or parsed['result'].get('isError'):
            raise RuntimeError('unexpected stdio result')
        payloads.append(json.loads(parsed['result']['content'][0]['text']))
    byte_count = lambda indices: sum(len(lines[i].encode('utf-8')) + len(responses[i]) for i in indices)
    rows = []
    registry = {tool['name']: tool['inputSchema'] for tool in TOOLS}
    for query, selected, baseline, candidate in cases:
        before, index = payloads[baseline[0]], payloads[candidate[0]]
        if [m['name'] for m in before['matches']] != [m['name'] for m in index['matches']]:
            raise RuntimeError('discovery identifiers changed')
        for indices in (baseline, candidate):
            if payloads[indices[-1]]['matches'][0]['inputSchema'] != registry[selected]:
                raise RuntimeError('selected schema was not recovered exactly')
        rows.append({'query': query, 'selected_tool': selected,
                     'baseline_calls': len(baseline), 'index_calls': len(candidate),
                     'baseline_exchange_bytes': byte_count(baseline),
                     'index_exchange_bytes': byte_count(candidate),
                     'same_identifiers': True, 'selected_schema_exact': True})
    total_before = sum(r['baseline_exchange_bytes'] for r in rows)
    total_after = sum(r['index_exchange_bytes'] for r in rows)
    print(json.dumps({'schema': 'botte.discovery-index-measurement/v1',
                      'origin': 'authored-queries-actual-stdio', 'catalog_tools': len(TOOLS),
                      'method': 'UTF-8 request plus response JSON-RPC bytes including newlines; both lookup exchanges counted',
                      'selection': 'first ranked tool; no task-quality validation',
                      'source_sha256': {str(p): hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in
                                        ('skills/llm_mcp/lazy.py', 'skills/llm_mcp/server.py')},
                      'rows': rows, 'total_baseline_bytes': total_before,
                      'total_index_bytes': total_after,
                      'byte_reduction_fraction': (total_before - total_after) / total_before,
                      'limits': ['provider tokens, cost and latency unmeasured',
                                 'index descriptions are lossy hints; full schemas must be loaded',
                                 'extra host/model roundtrip can outweigh byte reduction',
                                 'tools/list and host context registration excluded',
                                 'no backend connection or tool execution qualified']}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
