"""Contract and bounded-search checks for the MCP assignment tool."""
import itertools
import json
import os
import subprocess
import sys

import pytest
from skills.llm_mcp.server import _tool_assign_work
from skills.solvers import bin_pack


def call(tasks, workers=('a', 'b'), **options):
    return json.loads(_tool_assign_work({'tasks': tasks, 'workers': list(workers), **options}))


def test_weighted_and_decimal_costs_are_preserved():
    out = call(['A:5', ['B', 3], 'C:2'])
    assert out['total'] == 10
    assert out['makespan'] == 5
    out = call(['a:0.00001'], strategy='bounded')
    assert out['total'] == 0.00001
    assert out['search']['reason'] == 'unsupported_precision'
    assert not out['search']['optimal']


@pytest.mark.parametrize('args', [
    {'tasks': ['x'], 'workers': []},
    {'tasks': ['x'], 'workers': ['w', 'w']},
    {'tasks': ['x'], 'workers': [' ']},
    {'tasks': ['x:bad'], 'workers': ['w']},
    {'tasks': [['x', 9007199254740993]], 'workers': ['w']},
    {'tasks': ['x:0.10000000000000001'], 'workers': ['w']},
    {'tasks': ['a:1e308', 'b:1e308'], 'workers': ['w']},
    {'tasks': ['x'], 'workers': ['w'], 'budget_ms': 0},
    {'tasks': ['x'], 'workers': ['w'], 'strategy': 'bounded', 'budget_ms': 11},
    {'tasks': ['x'] * 1025, 'workers': ['w']},
    {'tasks': ['x'], 'workers': [f'w{i}' for i in range(65)]},
    {'tasks': ['x' * 513], 'workers': ['w']},
    {'tasks': [['x' * 257, 1]], 'workers': ['w']},
    {'tasks': [['x', '0' * 257]], 'workers': ['w']},
])
def test_invalid_requests_fail(args):
    with pytest.raises(ValueError):
        _tool_assign_work(args)


def test_bounded_search_matches_bruteforce_when_optimal():
    weights = [7, 6, 5, 4, 3]
    out = call([[str(i), x] for i, x in enumerate(weights)], strategy='bounded', budget_ms=10)
    optimum = min(max(sum(w for w, worker in zip(weights, assignment) if worker == j)
                      for j in (0, 1)) for assignment in itertools.product((0, 1), repeat=len(weights)))
    if out['search']['optimal']:
        assert out['makespan'] == optimum
    assert sorted(x['task'] for group in out['assignment'].values() for x in group) == [str(i) for i in range(5)]
    fallback = call(['a:4', 'b:3'], strategy='bounded', budget_ms=0)
    assert fallback['search']['reason'] == 'budget_disabled'
    assert not fallback['search']['optimal']


def test_stdio_lists_and_executes_contract():
    requests = [
        {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'},
        {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {'name': 'assign_work',
         'arguments': {'tasks': ['A:5', 'B:3', 'C:2'], 'workers': ['a', 'b']}}},
    ]
    result = subprocess.run([sys.executable, '-B', '-m', 'skills.llm_mcp.server'],
        input=''.join(json.dumps(r)+'\n' for r in requests), text=True, encoding='utf-8',
        capture_output=True, check=True, timeout=30,
        env=dict(os.environ, BOTTE_MCP_LAZY_TOOLS='0', PYTHONDONTWRITEBYTECODE='1'))
    messages = {x['id']: x for x in map(json.loads, result.stdout.splitlines()) if 'id' in x}
    tools = {x['name']: x for x in messages[1]['result']['tools']}
    assert 'bounded' in tools['assign_work']['inputSchema']['properties']['strategy']['enum']
    assert tools['assign_work']['inputSchema']['properties']['tasks']['maxItems'] == 1024
    assert tools['assign_work']['inputSchema']['properties']['workers']['maxItems'] == 64
    assert json.loads(messages[2]['result']['content'][0]['text'])['total'] == 10


def test_string_pair_cost_is_supported():
    assert call([['a', '2.5']])['total'] == 2.5
    assert call(['x' * 512])['total'] == 1
    assert call([['x' * 256, '2.5']])['total'] == 2.5


def test_oversized_item_is_reported_separately_from_bins():
    out = bin_pack([('large', 11), ('small', 3)], 10)
    assert out['oversize'] == [{'task': 'large', 'size': 11.0}]
    assert all(item['task'] != 'large' for bin_ in out['bins'] for item in bin_['items'])
    assert out['bin_count'] == 1
