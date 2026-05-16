# context-codebase/scripts/context_engine/sqlite_index.py
"""
SQLite index - high-speed KV query storage
"""
from __future__ import annotations
import json
import re
import sqlite3
from pathlib import Path
from typing import Optional


class SQLiteIndex:
    """SQLite-based chunk index using FTS5 for high-speed full text search"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize database schema with FTS5"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # FTS5 table
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(
                id UNINDEXED,
                path,
                start_line UNINDEXED,
                end_line UNINDEXED,
                kind,
                name,
                language,
                signals,
                preview,
                content_hash UNINDEXED,
                tokenize="unicode61"
            )
        """)

        conn.commit()
        conn.close()

    def upsert_chunks(self, chunks: list[dict]) -> None:
        """Batch insert chunks — drop and recreate FTS5 table for speed."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Drop and recreate is much faster than per-row DELETE+INSERT on FTS5
        cursor.execute("DROP TABLE IF EXISTS chunks")
        cursor.execute("""
            CREATE VIRTUAL TABLE chunks USING fts5(
                id UNINDEXED,
                path,
                start_line UNINDEXED,
                end_line UNINDEXED,
                kind,
                name,
                language,
                signals,
                preview,
                content_hash UNINDEXED,
                tokenize="unicode61"
            )
        """)

        rows = [
            (
                chunk.get("id", ""),
                chunk.get("path", ""),
                chunk.get("startLine"),
                chunk.get("endLine"),
                chunk.get("kind", ""),
                chunk.get("name", ""),
                chunk.get("language", ""),
                json.dumps(chunk.get("signals", [])),
                chunk.get("preview", "")[:200],
                chunk.get("content_hash", ""),
            )
            for chunk in chunks
        ]
        cursor.executemany("""
            INSERT INTO chunks
            (id, path, start_line, end_line, kind, name, language, signals, preview, content_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)

        conn.commit()
        conn.close()

    def upsert_chunks_incremental(self, chunks: list[dict], changed_paths: set[str]) -> None:
        """Incremental FTS5 update — only delete and re-insert chunks for changed paths.

        Args:
            chunks: Full list of all chunks in the current index state.
            changed_paths: Set of file paths whose chunks should be replaced.
                          Paths in this set but absent from ``chunks`` (deleted files)
                          will have their old chunks removed from the FTS5 index.
        """
        if not changed_paths:
            return

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 1. Delete old chunks for all changed paths
        for path in changed_paths:
            normalized_path = path.replace('"', '').strip()
            if normalized_path:
                cursor.execute("DELETE FROM chunks WHERE path = ?", (normalized_path,))

        # 2. Insert only chunks belonging to changed paths
        rows = [
            (
                chunk.get("id", ""),
                chunk.get("path", ""),
                chunk.get("startLine"),
                chunk.get("endLine"),
                chunk.get("kind", ""),
                chunk.get("name", ""),
                chunk.get("language", ""),
                json.dumps(chunk.get("signals", [])),
                chunk.get("preview", "")[:200],
                chunk.get("content_hash", ""),
            )
            for chunk in chunks
            if chunk.get("path", "") in changed_paths
        ]
        if rows:
            cursor.executemany("""
                INSERT INTO chunks
                (id, path, start_line, end_line, kind, name, language, signals, preview, content_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, rows)

        conn.commit()
        conn.close()

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """Search chunks using FTS5 MATCH with strict and relaxed expressions."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        expressions = self._build_match_expressions(query)
        if not expressions:
            conn.close()
            return []

        results: list[dict] = []
        seen_ids: set[str] = set()
        for expression in expressions:
            try:
                cursor.execute("""
                    SELECT *, bm25(chunks) AS score
                    FROM chunks
                    WHERE chunks MATCH ?
                    ORDER BY score ASC
                    LIMIT ?
                """, (expression, limit))
            except sqlite3.OperationalError:
                continue

            for row in cursor.fetchall():
                chunk_id = row["id"]
                if not chunk_id or chunk_id in seen_ids:
                    continue
                seen_ids.add(chunk_id)
                results.append({
                    "id": chunk_id,
                    "path": row["path"],
                    "startLine": row["start_line"],
                    "endLine": row["end_line"],
                    "kind": row["kind"],
                    "name": row["name"],
                    "language": row["language"],
                    "signals": json.loads(row["signals"]) if row["signals"] else [],
                    "preview": row["preview"]
                })
                if len(results) >= limit:
                    break
            if len(results) >= limit:
                break

        conn.close()
        return results

    def _build_match_expressions(self, query: str) -> list[str]:
        terms = self._tokenize_query(query)
        if not terms:
            return []

        quoted_terms = [f'"{term}"' for term in terms[:8]]
        prefix_terms = [self._prefix_query_term(term) for term in terms[:8]]
        expressions = [
            " ".join(quoted_terms),  # strict AND-like match
            " AND ".join(prefix_terms),  # prefix AND for plural/camel variants
            " OR ".join(prefix_terms),  # relaxed OR fallback
        ]

        deduped: list[str] = []
        seen = set()
        for expression in expressions:
            normalized = expression.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(normalized)
        return deduped

    def _tokenize_query(self, query: str) -> list[str]:
        if not query:
            return []

        normalized = query.replace('"', ' ').strip().lower()
        if not normalized:
            return []
        tokens = re.findall(r'[A-Za-z0-9_]+|[\u4e00-\u9fff]+', normalized)

        deduped: list[str] = []
        seen = set()
        for token in tokens:
            if len(token) < 2 or token in seen:
                continue
            seen.add(token)
            deduped.append(token)
        return deduped

    def _prefix_query_term(self, term: str) -> str:
        if re.fullmatch(r'[A-Za-z0-9_]+', term) and len(term) >= 3:
            return f'{term}*'
        return f'"{term}"'

    def get_by_path(self, path: str) -> list[dict]:
        """Get all chunks for a specific path"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        normalized_path = path.replace('"', '').strip()
        if not normalized_path:
            conn.close()
            return []
        try:
            # Path is an exact key-like field; prefer exact equality over full-text MATCH.
            cursor.execute("SELECT * FROM chunks WHERE path = ?", (normalized_path,))
            
            results = []
            for row in cursor.fetchall():
                results.append({
                    "id": row["id"],
                    "path": row["path"],
                    "startLine": row["start_line"],
                    "endLine": row["end_line"],
                    "kind": row["kind"],
                    "name": row["name"],
                    "language": row["language"],
                    "signals": json.loads(row["signals"]) if row["signals"] else [],
                    "preview": row["preview"]
                })
        except sqlite3.OperationalError:
            results = []

        conn.close()
        return results

    def delete_stale(self, valid_ids: set[str]) -> None:
        """Delete chunks not in valid_ids"""
        if not valid_ids:
            return

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Need to read all IDs since FTS5 doesn't easily support NOT IN for unindexed columns like standard tables
        cursor.execute("SELECT id FROM chunks")
        all_ids = {row["id"] for row in cursor.fetchall()}
        
        to_delete = all_ids - valid_ids
        for stale_id in to_delete:
            cursor.execute("DELETE FROM chunks WHERE id = ?", (stale_id,))

        conn.commit()
        conn.close()

    def close(self):
        """Close connection"""
        pass
