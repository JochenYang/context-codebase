# context-codebase/tests/test_search_ranking.py
"""
Tests for HybridSearchRanker — multi-stage hybrid search.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / 'scripts'
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from context_engine.search_ranking import (
    HybridSearchRanker,
    _extract_symbol_candidates,
    _split_identifier,
    _camel_case_prefix_match,
)


def _make_chunk(
    chunk_id: str,
    path: str,
    name: str = "",
    kind: str = "function",
    signals: list[str] | None = None,
    preview: str = "",
    content: str = "",
    language: str = "python",
    start_line: int = 1,
    end_line: int = 10,
) -> dict:
    return {
        "id": chunk_id,
        "path": path,
        "name": name,
        "kind": kind,
        "signals": signals or [],
        "preview": preview,
        "content": content,
        "language": language,
        "startLine": start_line,
        "endLine": end_line,
    }


# ======================================================================
# Unit tests for helper functions
# ======================================================================

class TestSplitIdentifier(unittest.TestCase):
    """_split_identifier — CamelCase / snake_case segmentation."""

    def test_camel_case(self):
        self.assertEqual(_split_identifier("UserAuthService"), ["User", "Auth", "Service"])

    def test_snake_case(self):
        self.assertEqual(_split_identifier("user_auth_service"), ["user", "auth", "service"])

    def test_screaming_snake(self):
        self.assertEqual(_split_identifier("USER_AUTH"), ["USER", "AUTH"])

    def test_single_word(self):
        self.assertEqual(_split_identifier("main"), ["main"])

    def test_acronym_handling_userAuth(self):
        """UserAuth -> User Auth"""
        result = _split_identifier("UserAuth")
        self.assertIn("User", result)
        self.assertIn("Auth", result)

    def test_acronym_handling_HTTPServer(self):
        """HTTPServer -> HTTP, Server"""
        result = _split_identifier("HTTPServer")
        self.assertIn("HTTP", result)
        self.assertIn("Server", result)


class TestExtractSymbolCandidates(unittest.TestCase):
    """_extract_symbol_candidates — extract symbols from natural language queries."""

    def test_simple_keywords(self):
        candidates = _extract_symbol_candidates("user auth service")
        lower = {c.lower() for c in candidates}
        self.assertIn("user", lower)
        self.assertIn("auth", lower)
        self.assertIn("service", lower)

    def test_camel_case_query(self):
        candidates = _extract_symbol_candidates("UserAuthService")
        lower = {c.lower() for c in candidates}
        self.assertIn("userauthservice", lower)
        self.assertIn("user", lower)
        self.assertIn("auth", lower)
        self.assertIn("service", lower)

    def test_mixed_query(self):
        """Chinese + English query still extracts English symbols."""
        candidates = _extract_symbol_candidates("用户认证 auth service")
        lower = {c.lower() for c in candidates}
        self.assertIn("auth", lower)
        self.assertIn("service", lower)

    def test_short_tokens_excluded(self):
        candidates = _extract_symbol_candidates("a b c")
        self.assertEqual(len(candidates), 0)

    def test_no_duplicates(self):
        candidates = _extract_symbol_candidates("auth auth Auth")
        # "auth" appears once, "Auth" -> "auth" case-insensitive dedup
        lower = [c.lower() for c in candidates]
        self.assertEqual(lower.count("auth"), 1)


class TestCamelCasePrefixMatch(unittest.TestCase):
    """_camel_case_prefix_match — prefix match against CamelCase segments."""

    def test_prefix_matches_segment(self):
        self.assertTrue(_camel_case_prefix_match("Auth", "UserAuthService"))

    def test_prefix_does_not_match(self):
        self.assertFalse(_camel_case_prefix_match("Xyz", "UserAuthService"))

    def test_case_insensitive(self):
        self.assertTrue(_camel_case_prefix_match("auth", "UserAuthService"))

    def test_full_segment_match(self):
        self.assertTrue(_camel_case_prefix_match("Service", "UserAuthService"))


# ======================================================================
# HybridSearchRanker tests
# ======================================================================

class TestHybridSearchRanker(unittest.TestCase):
    """Core ranking pipeline."""

    def setUp(self):
        self.chunks = [
            _make_chunk("auth.py:1-10", "src/auth.py", "UserAuthService",
                        kind="function", signals=["auth", "login"],
                        preview="def authenticate(): pass",
                        content="def authenticate():\n    return True\n"),
            _make_chunk("auth.py:12-20", "src/auth.py", "LoginHandler",
                        kind="class", signals=["login", "handler"],
                        preview="class LoginHandler:",
                        content="class LoginHandler:\n    def handle(self): pass\n"),
            _make_chunk("router.py:1-10", "src/router.py", "RouteMessage",
                        kind="function", signals=["route", "message"],
                        preview="def route_message(): pass",
                        content="def route_message():\n    return payload\n"),
            _make_chunk("model.py:1-10", "src/model.py", "UserModel",
                        kind="model", signals=["user", "schema"],
                        preview="class UserModel:",
                        content="class UserModel:\n    name = StringField()\n"),
            _make_chunk("service.py:1-10", "src/service.py", "AuthService",
                        kind="class", signals=["auth", "business"],
                        preview="class AuthService:",
                        content="class AuthService:\n    def login(self): pass\n"),
            _make_chunk("doc.md:1-10", "docs/guide.md", "",
                        kind="section", signals=["documentation"],
                        preview="## Getting Started\nWelcome...",
                        content="## Getting Started\nWelcome to the project\n"),
            _make_chunk("test_auth.py:1-10", "tests/test_auth.py", "TestAuth",
                        kind="function", signals=["test", "auth"],
                        preview="def test_login():",
                        content="def test_login():\n    assert True\n"),
        ]
        self.important_ranks = {"src/auth.py": 0, "src/router.py": 3, "src/service.py": 5}
        self.recent_changed = {"src/auth.py"}
        self.file_dep_map = {"src/router.py": ["src/auth.py"]}
        self.ranker = HybridSearchRanker(
            important_ranks=self.important_ranks,
            recent_changed=self.recent_changed,
            file_dependency_map=self.file_dep_map,
        )

    # ---- Signal A: exact symbol match ----

    def test_exact_symbol_match_ranked_highest(self):
        """Query matching a symbol name exactly gets top score."""
        results = self.ranker.rank("UserAuthService", self.chunks, limit=5)
        self.assertTrue(results, "should return results")
        top = results[0]
        self.assertEqual(top["name"], "UserAuthService",
                         "exact symbol match should rank first")
        self.assertIn("exact symbol match", top["reasons"][0])

    def test_exact_symbol_case_insensitive(self):
        """Case-insensitive exact match still scores highly."""
        results = self.ranker.rank("userauthservice", self.chunks, limit=5)
        self.assertTrue(results)
        self.assertEqual(results[0]["name"], "UserAuthService")

    # ---- Signal B: CamelCase prefix ----

    def test_camel_case_prefix_boost(self):
        """Query 'Auth' matches 'AuthService' via CamelCase prefix."""
        results = self.ranker.rank("Auth", self.chunks, limit=5)
        top_names = [r["name"] for r in results]
        # AuthService and UserAuthService both start with "Auth"
        self.assertTrue(
            any("Auth" in n for n in top_names),
            f"expected Auth-prefixed symbols, got {top_names}",
        )

    # ---- Signal C: compound term match ----

    def test_compound_term_match(self):
        """Query 'user auth' matches 'UserAuthService' via compound matching."""
        results = self.ranker.rank("user auth", self.chunks, limit=5)
        top_names = [r["name"] for r in results]
        self.assertIn("UserAuthService", top_names,
                      "compound term match should find UserAuthService")

    # ---- Signal D: keyword overlap ----

    def test_keyword_overlap_fallback(self):
        """Query with no symbol match falls back to keyword overlap."""
        results = self.ranker.rank("route message", self.chunks, limit=5)
        top_names = [r["name"] for r in results]
        self.assertIn("RouteMessage", top_names,
                      "keyword overlap should find RouteMessage")

    def test_fts_fallback_content(self):
        """Query matching preview/content text finds relevant chunk."""
        results = self.ranker.rank("Getting Started project", self.chunks, limit=5)
        paths = [r["path"] for r in results]
        self.assertIn("docs/guide.md", paths,
                      "content match should find documentation chunk")

    # ---- Signal E: co-location boost ----

    def test_co_location_boost(self):
        """Query symbol matching a path component gets co-location boost."""
        results = self.ranker.rank("model", self.chunks, limit=5)
        top_paths = [r["path"] for r in results]
        self.assertIn("src/model.py", top_paths,
                      "co-location boost should rank model chunk higher")

    # ---- Signal F: important file boost ----

    def test_important_file_boost(self):
        """Files in important_ranks get a boost."""
        results = self.ranker.rank("handler login", self.chunks, limit=5)
        top_paths = [r["path"] for r in results]
        # src/auth.py has important_rank=0 and contains "handler" in signals
        self.assertIn("src/auth.py", top_paths)

    # ---- Signal G: recent change boost ----

    def test_recent_change_boost_bugfix_task(self):
        """Recent-change boost applies to bugfix-investigation task."""
        results = self.ranker.rank("authenticate", self.chunks,
                                   task="bugfix-investigation", limit=5)
        self.assertTrue(any(r["path"] == "src/auth.py" for r in results),
                        "recently changed file should rank high for bugfix task")

    # ---- Signal H: task relevance ----

    def test_task_relevance_feature_delivery(self):
        """Models and routes ranked higher for feature-delivery."""
        results = self.ranker.rank("data model", self.chunks,
                                   task="feature-delivery", limit=5)
        top_names = [r["name"] for r in results]
        self.assertIn("UserModel", top_names)

    # ---- Test file down-rank ----

    def test_test_file_downrank_feature_delivery(self):
        """Test files are downranked for feature-delivery task vs non-test files."""
        results = self.ranker.rank("login handler", self.chunks,
                                   task="feature-delivery", limit=10)
        top_paths = [r["path"] for r in results]
        # Non-test file should appear before test file
        test_positions = [i for i, p in enumerate(top_paths) if "test" in p.lower()]
        impl_positions = [i for i, p in enumerate(top_paths) if "test" not in p.lower()]
        if test_positions and impl_positions:
            self.assertLess(impl_positions[0], test_positions[0],
                            "implementation file should rank above test file")

    # ---- Diversity cap ----

    def test_diversity_cap(self):
        """No more than 30% results from the same file."""
        # Many chunks from src/auth.py
        many_chunks = [
            _make_chunk(f"auth.py:{i*10}-{(i+1)*10}",
                        "src/auth.py",
                        f"Func{i}", kind="function")
            for i in range(20)
        ]
        # One unique chunk from another file
        many_chunks.append(
            _make_chunk("other.py:1-10", "src/other.py", "UniqueFunc")
        )

        results = self.ranker.rank("Func", many_chunks, limit=10)
        file_counts = {}
        for r in results:
            file_counts[r["path"]] = file_counts.get(r["path"], 0) + 1

        # At most 3 results from src/auth.py (30% of 10)
        self.assertLessEqual(
            file_counts.get("src/auth.py", 0), 3,
            f"diversity cap violated: {file_counts}",
        )

    # ---- Edge cases ----

    def test_empty_query(self):
        """Empty query returns no results."""
        results = self.ranker.rank("", self.chunks, limit=5)
        self.assertEqual(len(results), 0)

    def test_empty_chunks(self):
        """Empty chunks list returns no results."""
        results = self.ranker.rank("auth", [], limit=5)
        self.assertEqual(len(results), 0)

    def test_no_match_falls_back_to_important_files(self):
        """Query with no plausible match falls back to file-rank signals."""
        results = self.ranker.rank("xyznonexistent9999", self.chunks, limit=5)
        # Should return meaningful fallback (important files + task-relevant chunks)
        # but all scores should be low since no query signal matched
        self.assertGreater(len(results), 0,
                           "fallback should still return results")
        self.assertLess(results[0]["score"], 50,
                        "fallback scores should be low, got %s" % results[0]["score"])


# ======================================================================
# Integration with retrieval.py
# ======================================================================

class TestRetrieveChunksHybridFlag(unittest.TestCase):
    """retrieve_chunks with use_hybrid=True/False produces compatible results."""

    def setUp(self):
        # Re-import with updated module
        import importlib
        self.retrieval = importlib.import_module("context_engine.retrieval")

    def test_hybrid_vs_legacy_shapes(self):
        """Both modes produce same output shape."""
        chunks = [
            _make_chunk("a.py:1-10", "src/a.py", "AuthService",
                        kind="function", signals=["auth"],
                        preview="def auth(): pass"),
            _make_chunk("b.py:1-10", "src/b.py", "UserModel",
                        kind="model", signals=["user"],
                        preview="class UserModel:"),
        ]
        important_ranks = {"src/a.py": 0}
        recent = set()
        dep_map = {}

        hybrid = self.retrieval.retrieve_chunks(
            "auth", chunks, important_ranks, recent, dep_map,
            task="understand-project", limit=5, use_hybrid=True,
        )
        legacy = self.retrieval.retrieve_chunks(
            "auth", chunks, important_ranks, recent, dep_map,
            task="understand-project", limit=5, use_hybrid=False,
        )

        for results in [hybrid, legacy]:
            for r in results:
                self.assertIn("id", r)
                self.assertIn("path", r)
                self.assertIn("score", r)
                self.assertIn("reasons", r)
                self.assertIn("preview", r)

    def test_hybrid_default_true(self):
        """Default value for use_hybrid is True."""
        chunks = [
            _make_chunk("a.py:1-10", "src/a.py", "testFunc",
                        kind="function", signals=[], preview="def testFunc(): pass"),
        ]
        result = self.retrieval.retrieve_chunks(
            "testFunc", chunks, {}, set(), {},
            task="understand-project", limit=5,
        )
        self.assertEqual(len(result), 1)

    def test_hybrid_camel_case_edge(self):
        """Hybrid mode finds symbols via CamelCase prefix that legacy might miss."""
        chunks = [
            _make_chunk("transport.py:1-10", "src/transport.py",
                        "TransportSearchAction",
                        kind="function", signals=["search"],
                        preview="def search(): pass"),
            _make_chunk("basic.py:1-10", "src/basic.py",
                        "BasicSearch",
                        kind="function", signals=["search"],
                        preview="def search(): pass"),
        ]

        hybrid = self.retrieval.retrieve_chunks(
            "search", chunks, {}, set(), {},
            task="understand-project", limit=5, use_hybrid=True,
        )
        hybrid_names = {r["name"] for r in hybrid}
        self.assertIn("TransportSearchAction", hybrid_names,
                      "hybrid should find CamelCase prefix matches")


if __name__ == "__main__":
    unittest.main()
