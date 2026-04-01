# context-codebase/scripts/context_engine/semantic_chunker.py
"""
语义分块器 - 基于 AST 边界的智能分块
"""
from __future__ import annotations
import ast
import hashlib
from dataclasses import dataclass
from typing import Iterator

SMALL_FILE_LINES = 60
MEDIUM_FILE_LINES = 150

class SemanticChunker:
    """基于 AST 的语义感知分块器"""

    def chunk_file(self, content: str, filepath: str, language: str) -> list[dict]:
        """对文件进行语义分块"""
        # 统一路径格式，避免 Windows 反斜杠导致 ID 格式错误
        filepath = filepath.replace('\\', '/')
        lines = content.splitlines()
        total_lines = len(lines)

        # 小文件保持原样（<60 行整块，>=60 行按 AST 边界分块）
        if total_lines < SMALL_FILE_LINES:
            return [self._create_chunk(filepath, 1, total_lines, "section", "", content, language)]

        # 解析 AST
        try:
            tree = ast.parse(content)
        except SyntaxError:
            # 解析失败时按固定行数分
            return self._chunk_by_lines(content, filepath, language)

        # 根据文件大小选择分块策略
        return self._chunk_by_ast_boundaries(tree, content, filepath, language)

    def _chunk_by_ast_boundaries(self, tree: ast.AST, content: str, filepath: str, language: str) -> list[dict]:
        """基于 AST 边界分块（仅顶层节点）"""
        chunks = []
        lines = content.splitlines()

        # 只处理顶层节点（Module 的直接子节点）
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if hasattr(node, 'lineno') and hasattr(node, 'end_lineno'):
                    start = node.lineno
                    end = node.end_lineno

                    if start and end:
                        chunk_lines = lines[start-1:end]
                        chunk_content = '\n'.join(chunk_lines)

                        kind = "class" if isinstance(node, ast.ClassDef) else "function"
                        name = node.name
                        signals = self._extract_signals(chunk_content, name, language)

                        chunks.append({
                            "id": f"{filepath}:{start}-{end}",
                            "path": filepath,
                            "startLine": start,
                            "endLine": end,
                            "kind": kind,
                            "name": name,
                            "signals": signals,
                            "content": chunk_content,
                            "preview": chunk_content[:200],
                            "language": language
                        })

        # 如果没有 AST 节点，按行分
        if not chunks:
            return self._chunk_by_lines(content, filepath, language)

        return chunks

    def _chunk_by_lines(self, content: str, filepath: str, language: str) -> list[dict]:
        """按固定行数分块（fallback）"""
        chunks = []
        lines = content.splitlines()
        total = len(lines)

        for i in range(0, total, SMALL_FILE_LINES):
            start = i + 1
            end = min(i + SMALL_FILE_LINES, total)
            chunk_lines = lines[i:i+SMALL_FILE_LINES]
            chunk_content = '\n'.join(chunk_lines)

            chunks.append({
                "id": f"{filepath}:{start}-{end}",
                "path": filepath,
                "startLine": start,
                "endLine": end,
                "kind": "section",
                "name": "",
                "signals": self._extract_signals(chunk_content, "", language),
                "content": chunk_content,
                "preview": chunk_content[:200],
                "language": language
            })

        return chunks

    def _extract_signals(self, content: str, name: str, language: str) -> list[str]:
        """提取语义信号"""
        import re
        signals = set()

        # 从名称提取
        if name:
            signals.update(re.findall(r'[a-z]+', name.lower()))

        # 从注释/docstring 提取
        docstrings = re.findall(r'"""(.*?)"""', content, re.DOTALL)
        docstrings += re.findall(r"'''(.*?)'''", content, re.DOTALL)
        for doc in docstrings:
            signals.update(re.findall(r'[a-z]+', doc.lower()))

        # 从代码关键词提取
        keywords = [
            'auth', 'login', 'password', 'token', 'jwt', 'session',
            'api', 'http', 'request', 'response', 'endpoint',
            'database', 'db', 'sql', 'query',
            'cache', 'redis', 'memcache',
            'file', 'upload', 'download', 'storage',
            'email', 'notification', 'webhook',
            'payment', 'stripe', 'billing',
            'config', 'settings', 'env',
            'error', 'exception', 'retry',
            'async', 'await', 'promise',
            'middleware', 'hook', 'filter',
            'validation', 'schema', 'type',
        ]
        content_lower = content.lower()
        for kw in keywords:
            if kw in content_lower:
                signals.add(kw)

        return sorted(list(signals))[:20]

    def _create_chunk(self, filepath: str, start: int, end: int, kind: str, name: str, content: str, language: str) -> dict:
        """创建单个 chunk"""
        return {
            "id": f"{filepath}:{start}-{end}",
            "path": filepath,
            "startLine": start,
            "endLine": end,
            "kind": kind,
            "name": name,
            "signals": self._extract_signals(content, name, language),
            "content": content,
            "preview": content[:200],
            "language": language
        }