"""Behavioral regressions for bounded MCP discovery (no backend calls)."""
import copy
import json
import unittest

from skills.llm_mcp.lazy import find_tool, MAX_DESCRIPTION_BYTES
from skills.llm_mcp.server import TOOLS, handle


def tool(name, description='search code', size=0):
    return {'name': name, 'description': description,
            'inputSchema': {'type': 'object', 'description': 'x' * size}}


class DiscoveryBudgetTests(unittest.TestCase):
    def test_exact_identifier_wins(self):
        exact = tool('inspect', '')
        noisy = tool('aaa', 'inspect')
        self.assertEqual(find_tool('inspect', [noisy, exact], top_k=1)['matches'][0]['name'], 'inspect')

    def test_registration_order_does_not_change_results(self):
        tools = [tool('z_search'), tool('a_search')]
        self.assertEqual(find_tool('search', tools), find_tool('search', tools[::-1]))

    def test_accented_terms_match(self):
        self.assertEqual(find_tool('résumé', [tool('resume', '')])['matches'][0]['name'], 'resume')

    def test_zero_budget_retains_discoverability(self):
        result = find_tool('search', [tool('search')], schema_budget_bytes=0)
        self.assertEqual(result['matches'][0]['schema_status'], 'deferred_budget')
        self.assertNotIn('inputSchema', result['matches'][0])
        self.assertEqual(result['schema_bytes_returned'], 0)

    def test_oversized_schema_does_not_hide_smaller_match(self):
        result = find_tool('search', [tool('a_search', size=1000), tool('z_search')], schema_budget_bytes=100)
        self.assertEqual([x['schema_status'] for x in result['matches']], ['deferred_budget', 'included'])
        self.assertLessEqual(result['schema_bytes_returned'], 100)

    def test_cumulative_budget_and_exact_boundary(self):
        schema = tool('search')['inputSchema']
        size = len(json.dumps(schema, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
        result = find_tool('search', [tool('a_search'), tool('b_search')], schema_budget_bytes=size)
        self.assertEqual([x['schema_status'] for x in result['matches']], ['included', 'deferred_budget'])
        self.assertEqual(result['schema_bytes_returned'], size)

    def test_unicode_bytes_and_description_bound(self):
        candidate = tool('search', 'é' * 1000)
        candidate['inputSchema']['description'] = 'é' * 100
        result = find_tool('search', [candidate])
        item = result['matches'][0]
        self.assertLessEqual(len(item['description'].encode('utf-8')), MAX_DESCRIPTION_BYTES)
        self.assertTrue(item['description_truncated'])
        self.assertEqual(result['schema_bytes_returned'], len(json.dumps(item['inputSchema'], ensure_ascii=False, separators=(',', ':')).encode('utf-8')))

    def test_results_cannot_mutate_registered_schema(self):
        tools = [tool('search')]
        before = copy.deepcopy(tools)
        find_tool('search', tools)['matches'][0]['inputSchema']['type'] = 'array'
        self.assertEqual(tools, before)

    def test_invalid_inputs_are_rejected(self):
        for kwargs in ({'query': []}, {'query': 'é' * 1025}, {'query': 'search', 'top_k': True},
                       {'query': 'search', 'top_k': '2'}, {'query': 'search', 'top_k': -1},
                       {'query': 'search', 'top_k': 11}, {'query': 'search', 'schema_budget_bytes': True},
                       {'query': 'search', 'schema_budget_bytes': -1},
                       {'query': 'search', 'schema_budget_bytes': 65537}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                find_tool(tools=[], **kwargs)

    def test_real_catalog_budget(self):
        for query in ('memory', 'verify', 'route', 'security', 'compress', 'docs'):
            with self.subTest(query=query):
                result = find_tool(query, TOOLS, schema_budget_bytes=512)
                self.assertLessEqual(result['schema_bytes_returned'], 512)
                self.assertTrue(result['matches'])
                self.assertTrue(all('name' in item for item in result['matches']))

    def test_bad_protocol_call_keeps_server_usable(self):
        for args in ({'query': 'route', 'top_k': 'oops'}, {'query': []},
                     {'query': 'route', 'unexpected': 1}, ['route']):
            with self.subTest(args=args):
                result = handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                                 'params': {'name': 'find_tool', 'arguments': args}})
                self.assertTrue(result['result']['isError'])
                self.assertIn('result', handle({'jsonrpc': '2.0', 'id': 2, 'method': 'ping'}))

    def test_protocol_budget_is_honored(self):
        result = handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                         'params': {'name': 'find_tool', 'arguments': {'query': 'memory', 'schema_budget_bytes': 0}}})
        payload = json.loads(result['result']['content'][0]['text'])
        self.assertTrue(payload['matches'])
        self.assertTrue(all('inputSchema' not in item for item in payload['matches']))


class DiscoveryIndexTests(unittest.TestCase):
    def test_index_keeps_same_ranked_identifiers(self):
        for query in ('memory', 'verify', 'route', 'security', 'compress', 'docs'):
            with self.subTest(query=query):
                full = find_tool(query, TOOLS)
                index = find_tool(query, TOOLS, detail='index')
                self.assertEqual([x['name'] for x in full['matches']], [x['name'] for x in index['matches']])
                self.assertFalse(index['schemas_included'])
                self.assertTrue(all('inputSchema' not in x for x in index['matches']))

    def test_every_registered_tool_can_be_resolved_from_index(self):
        for registered in TOOLS:
            with self.subTest(name=registered['name']):
                index = find_tool(registered['name'], TOOLS, detail='index', top_k=1)
                self.assertEqual(index['matches'][0]['name'], registered['name'])
                full = find_tool(index['matches'][0]['name'], TOOLS, top_k=1, schema_budget_bytes=65536)
                self.assertEqual(full['matches'][0]['inputSchema'], registered['inputSchema'])

    def test_index_never_serializes_schemas(self):
        # A non-JSON sentinel would fail schema serialization in normal mode.
        tools = [tool('search')]
        tools[0]['inputSchema'] = object()
        self.assertEqual(find_tool('search', tools, detail='index')['matches'][0]['name'], 'search')

    def test_index_unicode_bound_and_omissions(self):
        tools = [tool('search', 'é' * 1000)]
        item = find_tool('search', tools, detail='index')['matches'][0]
        self.assertLessEqual(len(item['description'].encode('utf-8')), 160)
        self.assertTrue(item['description_truncated'])
        self.assertNotIn('description_truncated', find_tool('search', [tool('search')], detail='index')['matches'][0])

    def test_default_mode_is_unchanged(self):
        self.assertEqual(find_tool('route', TOOLS), find_tool('route', TOOLS, detail='schemas'))

    def test_empty_index(self):
        self.assertEqual(find_tool('xyzzy_no_such_concept_qqq', TOOLS, detail='index')['matches'], [])

    def test_invalid_detail_and_protocol_recovery(self):
        for value in ('other', None, True, [], {}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                find_tool('route', TOOLS, detail=value)
            response = handle({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                               'params': {'name': 'find_tool', 'arguments': {'query': 'route', 'detail': value}}})
            self.assertTrue(response['result']['isError'])
        good = handle({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call',
                       'params': {'name': 'find_tool', 'arguments': {'query': 'route', 'detail': 'index'}}})
        self.assertEqual(json.loads(good['result']['content'][0]['text'])['schema'], 'botte.tool-discovery-index/v1')


if __name__ == '__main__':
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromNames([__name__ + ".DiscoveryBudgetTests", __name__ + ".DiscoveryIndexTests"]))
    print(f'{result.testsRun - len(result.failures) - len(result.errors)} passed, {len(result.failures) + len(result.errors)} failed')
    raise SystemExit(0 if result.wasSuccessful() else 1)
