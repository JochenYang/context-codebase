# context-codebase/tests/test_enhanced.py
"""Tests for enhanced modules: fuzzy_search, git_index"""
import os
import sys
import unittest

SCRIPT_DIR = os.path.join(os.path.dirname(__file__), '..', 'scripts')
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from context_engine.fuzzy_search import FuzzySymbolSearcher
from context_engine.git_index import enrich_chunks_with_git


class TestFuzzySymbolSearcher(unittest.TestCase):
    def setUp(self):
        self.searcher = FuzzySymbolSearcher()
        self.chunks = [
            {'id': 'c1', 'path': 'services/user.py', 'kind': 'function',
             'name': 'getUserById', 'language': 'python', 'startLine': 10, 'endLine': 20},
            {'id': 'c2', 'path': 'services/auth.py', 'kind': 'function',
             'name': 'authenticate_user', 'language': 'python', 'startLine': 5, 'endLine': 15},
            {'id': 'c3', 'path': 'models/user.py', 'kind': 'class',
             'name': 'UserModel', 'language': 'python', 'startLine': 1, 'endLine': 30},
            {'id': 'c4', 'path': 'utils/helpers.py', 'kind': 'function',
             'name': 'format_date', 'language': 'python', 'startLine': 1, 'endLine': 5},
        ]
        self.searcher.build_index(self.chunks)

    def test_exact_match(self):
        results = self.searcher.search('getUserById')
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0]['name'], 'getUserById')

    def test_camel_case_fuzzy(self):
        results = self.searcher.search('getUser')
        names = [r['name'] for r in results]
        self.assertIn('getUserById', names)

    def test_snake_case_match(self):
        results = self.searcher.search('authenticate_user')
        self.assertGreater(len(results), 0)

    def test_prefix_match(self):
        results = self.searcher.search('get')
        names = [r['name'] for r in results]
        self.assertIn('getUserById', names)

    def test_path_filter(self):
        results = self.searcher.search('User', path_filter='services')
        self.assertGreater(len(results), 0)
        for r in results:
            self.assertIn('services', r['path'])

    def test_round_trip_serialization(self):
        """to_dict() and from_dict() should preserve search behavior"""
        data = self.searcher.to_dict()
        restored = FuzzySymbolSearcher.from_dict(data)
        results = restored.search('getUserById')
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0]['name'], 'getUserById')

    def test_symbol_count(self):
        self.assertEqual(self.searcher.symbol_count, 4)


class TestGitEnrichment(unittest.TestCase):
    def test_enrich_chunks_with_git(self):
        chunks = [
            {'id': 'c1', 'path': 'hot.py', 'kind': 'function'},
            {'id': 'c2', 'path': 'cold.py', 'kind': 'function'},
        ]
        git_stats = {
            'changeFrequency': {'hot.py': 50, 'cold.py': 2},
            'hotspots': [{'path': 'hot.py', 'changes': 50}],
            'churnFiles': [{'path': 'hot.py', 'insertions': 100, 'deletions': 50}],
        }
        enriched = enrich_chunks_with_git(chunks, git_stats)
        self.assertEqual(enriched[0]['gitChangeFrequency'], 50)
        self.assertTrue(enriched[0]['gitHotspot'])
        self.assertEqual(enriched[0]['gitChurn'], 150)
        self.assertEqual(enriched[1]['gitChangeFrequency'], 2)
        self.assertFalse(enriched[1]['gitHotspot'])


if __name__ == '__main__':
    unittest.main()
