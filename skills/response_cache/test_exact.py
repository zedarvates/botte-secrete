"""Regression coverage for exact query identity, including persisted legacy keys."""
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest

from skills.response_cache import ResponseCache


class ExactCacheTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.cache = ResponseCache(self.directory.name)

    def test_whitespace_variants_do_not_share_responses(self):
        variants = ['a b', 'a  b', 'a\tb', 'a\nb', ' a b', 'a b ',
                    'a\r\nb', 'a\u00a0b', 'a\u2003b']
        for index, query in enumerate(variants):
            self.cache.set(query, str(index))
        reloaded = ResponseCache(self.directory.name)
        for index, query in enumerate(variants):
            with self.subTest(query=query):
                self.assertEqual(reloaded.get(query).response, str(index))

    def test_quoted_spaces_and_indentation_are_significant(self):
        for original, changed in [('Return exactly "a  b"', 'Return exactly "a b"'),
                                  ('if x:\n    y()', 'if x:\n y()')]:
            with self.subTest(original=original):
                self.cache.set(original, 'original')
                self.assertIsNone(self.cache.get(changed))
                self.assertEqual(self.cache.get(original).response, 'original')

    def seed_legacy(self, query):
        material = json.dumps({'query': ' '.join(query.split()), 'model': 'm', 'context': 'c'},
                              ensure_ascii=False, sort_keys=True)
        key = hashlib.sha256(material.encode('utf-8')).hexdigest()[:16]
        entry = {'query_hash': key, 'query': query, 'response': 'legacy',
                 'timestamp': time.time(), 'model': 'm', 'tokens_saved': 10}
        Path(self.directory.name, 'response_cache.json').write_text(json.dumps({key: entry}), encoding='utf-8')
        return ResponseCache(self.directory.name)

    def test_legacy_normalized_collision_is_not_a_hit(self):
        cache = self.seed_legacy('a  b')
        self.assertIsNone(cache.get_exact('a b', model='m', context='c'))
        self.assertEqual(cache.stats['hits_exact'], 0)
        self.assertEqual(cache.stats['tokens_saved'], 0)

    def test_legacy_noncanonical_query_can_be_recached(self):
        cache = self.seed_legacy('a  b')
        self.assertIsNone(cache.get_exact('a  b', model='m', context='c'))
        cache.set('a  b', 'fresh', model='m', context='c')
        reloaded = ResponseCache(self.directory.name)
        self.assertEqual(reloaded.get_exact('a  b', model='m', context='c').response, 'fresh')
        self.assertIsNone(reloaded.get_exact('a b', model='m', context='c'))

    def test_unchanged_legacy_identity_remains_usable(self):
        cache = self.seed_legacy('a b')
        self.assertEqual(cache.get_exact('a b', model='m', context='c').response, 'legacy')
        self.assertIsNone(cache.get_exact('a b', model='other', context='c'))
        self.assertIsNone(cache.get_exact('a b', model='m', context='other'))

    def test_case_and_empty_strings_remain_exact(self):
        for query in ('', ' ', 'A', 'a'):
            self.cache.set(query, repr(query))
        for query in ('', ' ', 'A', 'a'):
            self.assertEqual(self.cache.get(query).response, repr(query))


if __name__ == '__main__':
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(ExactCacheTests))
    failed = len({getattr(test, 'test_case', test).id()
                  for test, _ in result.failures + result.errors})
    print(f'{result.testsRun - failed} passed, {failed} failed')
    raise SystemExit(0 if result.wasSuccessful() else 1)
