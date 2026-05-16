# context-codebase/tests/test_graph.py
"""
Tests for graph.py — symbol graph model:
  - qualifiedName generation
  - function signature extraction
  - cross-file symbol reference edges
  - backward compatibility
  - stats correctness
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / 'scripts'
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from context_engine.graph import build_code_graph


# ======================================================================
# qualifiedName generation
# ======================================================================

class TestQualifiedName(unittest.TestCase):
    """qualifiedName field generation for all symbol kinds."""

    def test_function_qualified_name(self):
        result = build_code_graph(
            file_records=[{
                'path': 'src/service.ts',
                'language': 'TypeScript',
                'imports': [],
                'exports': [],
                'apiRoutes': [],
                'dataModels': [],
                'keyFunctions': [{'name': 'getUser', 'file': 'src/service.ts', 'line': 10}],
                'content': 'export function getUser(id: string) {\n  return id\n}\n',
            }],
            unique_routes=[],
            unique_models=[],
            key_functions=[],
            workspace={},
        )
        symbols = result['symbolIndex']
        self.assertEqual(len(symbols), 1)
        self.assertEqual(symbols[0]['qualifiedName'], 'src/service.ts::(function)getUser')

    def test_model_qualified_name(self):
        result = build_code_graph(
            file_records=[{
                'path': 'src/model.ts',
                'language': 'TypeScript',
                'imports': [],
                'exports': [],
                'apiRoutes': [],
                'dataModels': [{'name': 'User', 'type': 'class', 'line': 1}],
                'keyFunctions': [],
                'content': 'class User {}\n',
            }],
            unique_routes=[],
            unique_models=[],
            key_functions=[],
            workspace={},
        )
        symbols = result['symbolIndex']
        self.assertEqual(symbols[0]['qualifiedName'], 'src/model.ts::(model)User')

    def test_route_qualified_name(self):
        result = build_code_graph(
            file_records=[{
                'path': 'src/router.ts',
                'language': 'TypeScript',
                'imports': [],
                'exports': [],
                'apiRoutes': [{'method': 'GET', 'path': '/users', 'handler': 'src/router.ts'}],
                'dataModels': [],
                'keyFunctions': [],
                'content': '',
            }],
            unique_routes=[],
            unique_models=[],
            key_functions=[],
            workspace={},
        )
        symbols = result['symbolIndex']
        self.assertEqual(symbols[0]['qualifiedName'], 'src/router.ts::(route)GET /users')

    def test_qualified_name_unique_per_file(self):
        """Same symbol name in different files gets distinct qualifiedName."""
        result = build_code_graph(
            file_records=[
                {
                    'path': 'src/a.ts',
                    'language': 'TypeScript',
                    'imports': [],
                    'exports': ['getUser'],
                    'keyFunctions': [{'name': 'getUser', 'file': 'src/a.ts', 'line': 1}],
                    'apiRoutes': [],
                    'dataModels': [],
                    'content': 'export function getUser() {}\n',
                },
                {
                    'path': 'src/b.ts',
                    'language': 'TypeScript',
                    'imports': [],
                    'exports': ['getUser'],
                    'keyFunctions': [{'name': 'getUser', 'file': 'src/b.ts', 'line': 1}],
                    'apiRoutes': [],
                    'dataModels': [],
                    'content': 'export function getUser() {}\n',
                },
            ],
            unique_routes=[],
            unique_models=[],
            key_functions=[],
            workspace={},
        )
        qnames = {s['qualifiedName'] for s in result['symbolIndex']}
        self.assertEqual(len(qnames), 2)
        self.assertIn('src/a.ts::(function)getUser', qnames)
        self.assertIn('src/b.ts::(function)getUser', qnames)


# ======================================================================
# Function signature extraction
# ======================================================================

class TestFunctionSignature(unittest.TestCase):
    """Function signature extraction from file content."""

    def test_extract_signature_from_content(self):
        result = build_code_graph(
            file_records=[{
                'path': 'src/service.ts',
                'language': 'TypeScript',
                'imports': [],
                'exports': [],
                'apiRoutes': [],
                'dataModels': [],
                'keyFunctions': [{'name': 'findUser', 'file': 'src/service.ts', 'line': 2}],
                'content': (
                    '// comment\n'
                    'export function findUser(id: string): Promise<User> {\n'
                    '  return db.find(id)\n'
                    '}\n'
                ),
            }],
            unique_routes=[],
            unique_models=[],
            key_functions=[],
            workspace={},
        )
        symbols = result['symbolIndex']
        self.assertEqual(symbols[0]['signature'], 'export function findUser(id: string): Promise<User> {')

    def test_signature_truncated_at_120_chars(self):
        long_line = 'x' * 200
        result = build_code_graph(
            file_records=[{
                'path': 'src/long.ts',
                'language': 'TypeScript',
                'imports': [],
                'exports': [],
                'apiRoutes': [],
                'dataModels': [],
                'keyFunctions': [{'name': 'longFunc', 'file': 'src/long.ts', 'line': 1}],
                'content': long_line + '\n',
            }],
            unique_routes=[],
            unique_models=[],
            key_functions=[],
            workspace={},
        )
        self.assertEqual(len(result['symbolIndex'][0]['signature']), 120)

    def test_no_signature_for_non_function_symbols(self):
        result = build_code_graph(
            file_records=[{
                'path': 'src/model.ts',
                'language': 'TypeScript',
                'imports': [],
                'exports': [],
                'apiRoutes': [],
                'dataModels': [{'name': 'User', 'type': 'class', 'line': 1}],
                'keyFunctions': [],
                'content': 'class User {}\n',
            }],
            unique_routes=[],
            unique_models=[],
            key_functions=[],
            workspace={},
        )
        # model symbols should not have signature field
        self.assertNotIn('signature', result['symbolIndex'][0])


# ======================================================================
# Cross-file symbol reference edges
# ======================================================================

class TestSymbolEdges(unittest.TestCase):
    """Cross-file symbol reference edge generation."""

    def test_calls_edge_on_name_match(self):
        """A imports B, both have same-named function → calls edge."""
        result = build_code_graph(
            file_records=[
                {
                    'path': 'src/a.ts',
                    'language': 'TypeScript',
                    'imports': ['./b'],
                    'exports': ['findUser'],
                    'keyFunctions': [{'name': 'findUser', 'file': 'src/a.ts', 'line': 1}],
                    'apiRoutes': [],
                    'dataModels': [],
                    'content': 'export function findUser() {}\n',
                },
                {
                    'path': 'src/b.ts',
                    'language': 'TypeScript',
                    'imports': [],
                    'exports': ['findUser'],
                    'keyFunctions': [{'name': 'findUser', 'file': 'src/b.ts', 'line': 1}],
                    'apiRoutes': [],
                    'dataModels': [],
                    'content': 'export function findUser() {}\n',
                },
            ],
            unique_routes=[],
            unique_models=[],
            key_functions=[],
            workspace={},
        )
        self.assertGreater(result['symbolEdgeCount'], 0)
        self.assertEqual(len(result['symbolEdges']), 1)
        edge = result['symbolEdges'][0]
        self.assertEqual(edge['source'], 'src/a.ts::(function)findUser')
        self.assertEqual(edge['target'], 'src/b.ts::(function)findUser')
        self.assertEqual(edge['kind'], 'calls')
        self.assertEqual(edge['confidence'], 'inferred')

    def test_no_edge_without_name_match(self):
        """No calls edge when names don't match across files."""
        result = build_code_graph(
            file_records=[
                {
                    'path': 'src/service/UserService.ts',
                    'language': 'TypeScript',
                    'imports': ['../repo/UserRepo'],
                    'exports': [],
                    'keyFunctions': [{'name': 'getUser', 'file': 'src/service/UserService.ts', 'line': 5}],
                    'apiRoutes': [],
                    'dataModels': [],
                    'content': 'export function getUser() {}\n',
                },
                {
                    'path': 'src/repo/UserRepo.ts',
                    'language': 'TypeScript',
                    'imports': [],
                    'exports': ['findById'],
                    'keyFunctions': [{'name': 'findById', 'file': 'src/repo/UserRepo.ts', 'line': 3}],
                    'apiRoutes': [],
                    'dataModels': [],
                    'content': 'export function findById(id: string) {}\n',
                },
            ],
            unique_routes=[],
            unique_models=[],
            key_functions=[],
            workspace={},
        )
        self.assertEqual(result['symbolEdgeCount'], 0)

    def test_multiple_matches_create_multiple_edges(self):
        """Multiple matching symbols create multiple edges."""
        result = build_code_graph(
            file_records=[
                {
                    'path': 'src/svc.ts',
                    'language': 'TypeScript',
                    'imports': ['./repo'],
                    'exports': ['findUser', 'findPost'],
                    'keyFunctions': [
                        {'name': 'findUser', 'file': 'src/svc.ts', 'line': 1},
                        {'name': 'findPost', 'file': 'src/svc.ts', 'line': 3},
                    ],
                    'apiRoutes': [],
                    'dataModels': [],
                    'content': 'export function findUser() {}\nexport function findPost() {}\n',
                },
                {
                    'path': 'src/repo.ts',
                    'language': 'TypeScript',
                    'imports': [],
                    'exports': ['findUser', 'findPost'],
                    'keyFunctions': [
                        {'name': 'findUser', 'file': 'src/repo.ts', 'line': 1},
                        {'name': 'findPost', 'file': 'src/repo.ts', 'line': 3},
                    ],
                    'apiRoutes': [],
                    'dataModels': [],
                    'content': 'export function findUser() {}\nexport function findPost() {}\n',
                },
            ],
            unique_routes=[],
            unique_models=[],
            key_functions=[],
            workspace={},
        )
        self.assertEqual(result['symbolEdgeCount'], 2)
        kinds = {e['kind'] for e in result['symbolEdges']}
        self.assertEqual(kinds, {'calls'})

    def test_route_model_no_calls_edge(self):
        """Routes and models without function symbols don't create calls edges."""
        result = build_code_graph(
            file_records=[
                {
                    'path': 'src/router.ts',
                    'language': 'TypeScript',
                    'imports': ['./service'],
                    'exports': [],
                    'apiRoutes': [{'method': 'GET', 'path': '/users', 'handler': 'src/router.ts'}],
                    'dataModels': [],
                    'keyFunctions': [],
                    'content': 'app.get("/users", handler)\n',
                },
                {
                    'path': 'src/service.ts',
                    'language': 'TypeScript',
                    'imports': [],
                    'exports': [],
                    'apiRoutes': [],
                    'dataModels': [],
                    'keyFunctions': [],
                    'content': '',
                },
            ],
            unique_routes=[],
            unique_models=[],
            key_functions=[],
            workspace={},
        )
        self.assertEqual(result['symbolEdgeCount'], 0)


# ======================================================================
# Backward compatibility
# ======================================================================

class TestBackwardCompatibility(unittest.TestCase):
    """Backward compatibility with empty / missing fields."""

    def test_empty_imports_exports(self):
        """No crash when records have empty imports/exports."""
        result = build_code_graph(
            file_records=[{
                'path': 'src/main.ts',
                'language': 'TypeScript',
                'imports': [],
                'exports': [],
                'apiRoutes': [],
                'dataModels': [],
                'keyFunctions': [],
                'content': '',
            }],
            unique_routes=[],
            unique_models=[],
            key_functions=[],
            workspace={},
        )
        self.assertIn('symbolIndex', result)
        self.assertEqual(len(result['symbolIndex']), 0)
        self.assertEqual(result['symbolEdgeCount'], 0)
        self.assertIn('stats', result)

    def test_missing_content_field(self):
        """No crash when file record has no content field."""
        result = build_code_graph(
            file_records=[{
                'path': 'src/main.ts',
                'language': 'TypeScript',
                'imports': [],
                'exports': [],
                'apiRoutes': [],
                'dataModels': [],
                'keyFunctions': [{'name': 'main', 'file': 'src/main.ts', 'line': 1}],
            }],
            unique_routes=[],
            unique_models=[],
            key_functions=[],
            workspace={},
        )
        self.assertEqual(result['stats']['symbols'], 1)
        # signature should default to empty string via .get()
        self.assertEqual(result['symbolIndex'][0].get('signature', ''), '')

    def test_line_zero_does_not_crash(self):
        """line=0 doesn't cause signature extraction to crash."""
        result = build_code_graph(
            file_records=[{
                'path': 'src/main.ts',
                'language': 'TypeScript',
                'imports': [],
                'exports': [],
                'apiRoutes': [],
                'dataModels': [],
                'keyFunctions': [{'name': 'main', 'file': 'src/main.ts', 'line': 0}],
                'content': 'function main() {}\n',
            }],
            unique_routes=[],
            unique_models=[],
            key_functions=[],
            workspace={},
        )
        self.assertEqual(result['stats']['symbols'], 1)
        self.assertEqual(result['symbolIndex'][0].get('signature', ''), '')

    def test_line_none_does_not_crash(self):
        """line=None on a route symbol doesn't cause signature extraction to crash."""
        result = build_code_graph(
            file_records=[{
                'path': 'src/router.ts',
                'language': 'TypeScript',
                'imports': [],
                'exports': [],
                'apiRoutes': [{'method': 'GET', 'path': '/test', 'handler': 'src/router.ts'}],
                'dataModels': [],
                'keyFunctions': [],
                'content': 'app.get("/test", handler)\n',
            }],
            unique_routes=[],
            unique_models=[],
            key_functions=[],
            workspace={},
        )
        self.assertEqual(result['stats']['symbols'], 1)
        # route symbol should have qualifiedName without crashing
        self.assertIn('qualifiedName', result['symbolIndex'][0])

    def test_old_snapshot_access_pattern_safe(self):
        """Consumer using .get('symbolEdges', []) doesn't error on older version."""
        # Simulate old graph dict without the new fields
        old_graph: dict = {
            'stats': {'symbols': 5},
            'symbolIndex': [],
        }
        self.assertEqual(old_graph.get('symbolEdges', []), [])
        self.assertEqual(old_graph.get('symbolEdgeCount', 0), 0)
        for s in old_graph.get('symbolIndex', []):
            self.assertEqual(s.get('qualifiedName', ''), '')
            self.assertEqual(s.get('signature', ''), '')


# ======================================================================
# Stats correctness
# ======================================================================

class TestStatsCounts(unittest.TestCase):
    """Stats counts correctness."""

    def test_symbols_count_is_unique_qualified_names(self):
        result = build_code_graph(
            file_records=[{
                'path': 'src/main.ts',
                'language': 'TypeScript',
                'imports': [],
                'exports': [],
                'apiRoutes': [],
                'dataModels': [],
                'keyFunctions': [{'name': 'run', 'file': 'src/main.ts', 'line': 1}],
                'content': 'function run() {}\n',
            }],
            unique_routes=[],
            unique_models=[],
            key_functions=[],
            workspace={},
        )
        self.assertEqual(result['stats']['symbols'], 1)
        # New fields present
        self.assertIn('symbolEdges', result)
        self.assertIn('symbolEdgeCount', result)

    def test_symbol_count_with_multiple_kinds(self):
        result = build_code_graph(
            file_records=[{
                'path': 'src/main.ts',
                'language': 'TypeScript',
                'imports': [],
                'exports': ['getUser'],
                'apiRoutes': [],
                'dataModels': [{'name': 'User', 'type': 'class', 'line': 5}],
                'keyFunctions': [{'name': 'getUser', 'file': 'src/main.ts', 'line': 10}],
                'content': 'class User {}\nexport function getUser() {}\n',
            }],
            unique_routes=[],
            unique_models=[],
            key_functions=[],
            workspace={},
        )
        # One model (User) + one function (getUser) = 2 unique qualified names
        self.assertEqual(result['stats']['symbols'], 2)


# ======================================================================
# Run
# ======================================================================

if __name__ == '__main__':
    unittest.main()
