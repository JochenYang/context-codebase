# context-codebase 增强实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现语义分块、Chunk 级增量追踪、SQLite 索引和多语言支持的增强功能

**Architecture:** 通过新增独立模块（semantic_chunker.py、chunk_tracker.py、sqlite_index.py、multi_lang_analyzer.py）扩展现有 context_engine，保持向后兼容

**Tech Stack:** Python (内置 ast, sqlite3), go/parser, tree-sitter

---

## 实现顺序

1. semantic_chunker.py — 核心，依赖最少
2. chunk_tracker.py — 依赖 semantic_chunker
3. sqlite_index.py — 依赖 chunk_tracker
4. multi_lang_analyzer.py — 可独立测试
5. generate.py 集成 — 组装所有模块

---

## Task 1: 语义分块器 (semantic_chunker.py)

**Files:**
- Create: `context-codebase/scripts/context_engine/semantic_chunker.py`
- Test: `context-codebase/tests/test_semantic_chunker.py`

### Step 1: 创建测试文件

```python
# context-codebase/tests/test_semantic_chunker.py
import pytest
from context_engine.semantic_chunker import SemanticChunker, Chunk

class TestSemanticChunker:
    def test_chunk_small_file_unchanged(self):
        """小于60行的文件应保持原样"""
        content = """def foo():
    return 42

def bar():
    return 24
"""
        chunker = SemanticChunker()
        chunks = chunker.chunk_file(content, "test.py", language="python")
        
        assert len(chunks) == 1
        assert chunks[0]["kind"] == "section"
        assert chunks[0]["startLine"] == 1
        assert chunks[0]["endLine"] == 5

    def test_chunk_function_boundary(self):
        """基于函数边界分块"""
        content = """def authenticate(user):
    # 认证逻辑
    pass

def validate_token(token):
    # token 验证
    pass
"""
        chunker = SemanticChunker()
        chunks = chunker.chunk_file(content, "test.py", language="python")
        
        # 应该分成两个 chunk
        assert len(chunks) == 2
        assert chunks[0]["kind"] == "function"
        assert chunks[0]["name"] == "authenticate"
        assert chunks[1]["kind"] == "function"
        assert chunks[1]["name"] == "validate_token"

    def test_extract_signals(self):
        """提取语义信号"""
        content = """def process_payment(amount, currency):
    '''Process payment with Stripe.'''
    pass
"""
        chunker = SemanticChunker()
        chunks = chunker.chunk_file(content, "test.py", language="python")
        
        assert len(chunks) == 1
        signals = chunks[0]["signals"]
        assert "payment" in signals
        assert "stripe" in signals

    def test_class_chunking(self):
        """类级别的智能分块"""
        content = """class PaymentService:
    def __init__(self):
        pass
    
    def process(self, amount):
        pass
    
    def refund(self, transaction_id):
        pass
"""
        chunker = SemanticChunker()
        chunks = chunker.chunk_file(content, "test.py", language="python")
        
        # 整个类应作为一个 chunk
        assert len(chunks) == 1
        assert chunks[0]["kind"] == "class"
        assert chunks[0]["name"] == "PaymentService"
```

### Step 2: 创建语义分块器实现

```python
# context-codebase/scripts/context_engine/semantic_chunker.py
"""
语义分块器 - 基于 AST 边界的智能分块
"""
from __future__ import annotations
import ast
import hashlib
from dataclasses import dataclass
from typing import Iterator

@dataclass
class Chunk:
    id: str
    path: str
    start_line: int
    end_line: int
    kind: str  # function, class, section
    name: str
    signals: list[str]
    content: str
    preview: str
    language: str

SMALL_FILE_LINES = 60
MEDIUM_FILE_LINES = 150

class SemanticChunker:
    """基于 AST 的语义感知分块器"""
    
    def chunk_file(self, content: str, filepath: str, language: str) -> list[dict]:
        """对文件进行语义分块"""
        lines = content.splitlines()
        total_lines = len(lines)
        
        # 小文件保持原样
        if total_lines <= SMALL_FILE_LINES:
            return [self._create_chunk(filepath, 1, total_lines, "section", "", content, language)]
        
        # 解析 AST
        try:
            tree = ast.parse(content)
        except SyntaxError:
            # 解析失败时按固定行数分
            return self._chunk_by_lines(content, filepath, language)
        
        # 根据文件大小选择分块策略
        if total_lines <= MEDIUM_FILE_LINES:
            return self._chunk_by_ast_boundaries(tree, content, filepath, language)
        else:
            return self._chunk_by_ast_boundaries(tree, content, filepath, language)
    
    def _chunk_by_ast_boundaries(self, tree: ast.AST, content: str, filepath: str, language: str) -> list[dict]:
        """基于 AST 边界分块"""
        chunks = []
        lines = content.splitlines()
        
        for node in ast.walk(tree):
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
```

### Step 3: 运行测试

```bash
cd /d/codes/context-codebase
python -m pytest context-codebase/tests/test_semantic_chunker.py -v
```

### Step 4: 提交

```bash
git add context-codebase/scripts/context_engine/semantic_chunker.py
git add context-codebase/tests/test_semantic_chunker.py
git commit -m "feat: add semantic chunker with AST-based intelligent partitioning"
```

---

## Task 2: Chunk 追踪器 (chunk_tracker.py)

**Files:**
- Create: `context-codebase/scripts/context_engine/chunk_tracker.py`
- Test: `context-codebase/tests/test_chunk_tracker.py`

### Step 1: 创建测试文件

```python
# context-codebase/tests/test_chunk_tracker.py
import pytest
from context_engine.chunk_tracker import ChunkTracker, ChunkState, ChangeSet

class TestChunkTracker:
    def test_track_generates_stable_ids(self):
        """相同 chunk 应生成相同的 ID"""
        tracker = ChunkTracker()
        
        chunks = [
            {"id": "test.py:1-10", "content": "def foo():\n    pass"},
            {"id": "test.py:12-20", "content": "def bar():\n    pass"},
        ]
        
        states = tracker.track(chunks)
        
        assert "test.py:1-10" in states
        assert "test.py:12-20" in states
        assert states["test.py:1-10"].version == 1
    
    def test_detect_modified_chunk(self):
        """能检测到 chunk 的修改"""
        tracker = ChunkTracker()
        
        old_chunks = [
            {"id": "test.py:1-10", "content": "def foo():\n    return 1"},
        ]
        old_states = tracker.track(old_chunks)
        
        new_chunks = [
            {"id": "test.py:1-10", "content": "def foo():\n    return 42"},
        ]
        new_states = tracker.track(new_chunks)
        
        diff = tracker.diff(old_states, new_states)
        
        assert len(diff.modified) == 1
        assert diff.modified[0]["id"] == "test.py:1-10"
    
    def test_detect_added_chunk(self):
        """能检测到新增的 chunk"""
        tracker = ChunkTracker()
        
        old_chunks = [
            {"id": "test.py:1-10", "content": "def foo():\n    pass"},
        ]
        old_states = tracker.track(old_chunks)
        
        new_chunks = [
            {"id": "test.py:1-10", "content": "def foo():\n    pass"},
            {"id": "test.py:12-20", "content": "def bar():\n    pass"},
        ]
        new_states = tracker.track(new_chunks)
        
        diff = tracker.diff(old_states, new_states)
        
        assert len(diff.added) == 1
        assert diff.added[0]["id"] == "test.py:12-20"
    
    def test_detect_deleted_chunk(self):
        """能检测到删除的 chunk"""
        tracker = ChunkTracker()
        
        old_chunks = [
            {"id": "test.py:1-10", "content": "def foo():\n    pass"},
            {"id": "test.py:12-20", "content": "def bar():\n    pass"},
        ]
        old_states = tracker.track(old_chunks)
        
        new_chunks = [
            {"id": "test.py:1-10", "content": "def foo():\n    pass"},
        ]
        new_states = tracker.track(new_chunks)
        
        diff = tracker.diff(old_states, new_states)
        
        assert len(diff.deleted) == 1
        assert "test.py:12-20" in diff.deleted
    
    def test_unchanged_chunk_version_increment(self):
        """未变更的 chunk 版本不变"""
        tracker = ChunkTracker()
        
        chunks = [
            {"id": "test.py:1-10", "content": "def foo():\n    pass"},
        ]
        v1 = tracker.track(chunks)
        
        v2 = tracker.track(chunks)
        
        assert v1["test.py:1-10"].content_hash == v2["test.py:1-10"].content_hash
```

### Step 2: 创建 Chunk 追踪器实现

```python
# context-codebase/scripts/context_engine/chunk_tracker.py
"""
Chunk 级增量追踪器
"""
from __future__ import annotations
import hashlib
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class ChunkState:
    chunk_id: str
    content_hash: str
    version: int = 1

@dataclass
class ChangeSet:
    added: list[dict] = field(default_factory=list)
    modified: list[dict] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)

class ChunkTracker:
    """Chunk 级增量追踪器"""
    
    def track(self, chunks: list[dict]) -> dict[str, ChunkState]:
        """
        为每个 chunk 生成稳定的状态记录
        """
        states = {}
        
        for chunk in chunks:
            chunk_id = chunk["id"]
            content = chunk.get("content", "")
            content_hash = self._hash_content(content)
            
            states[chunk_id] = ChunkState(
                chunk_id=chunk_id,
                content_hash=content_hash,
                version=1
            )
        
        return states
    
    def diff(self, old: dict[str, ChunkState], new: dict[str, ChunkState]) -> ChangeSet:
        """
        比对两个状态集，返回变更集
        """
        change_set = ChangeSet()
        
        old_ids = set(old.keys())
        new_ids = set(new.keys())
        
        # 新增
        for chunk_id in new_ids - old_ids:
            change_set.added.append({"id": chunk_id})
        
        # 删除
        for chunk_id in old_ids - new_ids:
            change_set.deleted.append(chunk_id)
        
        # 修改和未变更
        for chunk_id in old_ids & new_ids:
            if old[chunk_id].content_hash != new[chunk_id].content_hash:
                change_set.modified.append({"id": chunk_id})
            else:
                change_set.unchanged.append(chunk_id)
        
        return change_set
    
    def merge_states(self, old: dict[str, ChunkState], new: dict[str, ChunkState]) -> dict[str, ChunkState]:
        """
        合并新旧状态，版本号递增
        """
        merged = dict(old)
        
        for chunk_id, state in new.items():
            if chunk_id in old:
                # 版本递增
                merged[chunk_id] = ChunkState(
                    chunk_id=chunk_id,
                    content_hash=state.content_hash,
                    version=old[chunk_id].version + 1
                )
            else:
                merged[chunk_id] = state
        
        return merged
    
    def _hash_content(self, content: str) -> str:
        """计算内容的 hash"""
        return hashlib.sha256(content.encode()).hexdigest()[:16]
```

### Step 3: 运行测试

```bash
cd /d/codes/context-codebase
python -m pytest context-codebase/tests/test_chunk_tracker.py -v
```

### Step 4: 提交

```bash
git add context-codebase/scripts/context_engine/chunk_tracker.py
git add context-codebase/tests/test_chunk_tracker.py
git commit -m "feat: add chunk tracker for incremental updates"
```

---

## Task 3: SQLite 索引 (sqlite_index.py)

**Files:**
- Create: `context-codebase/scripts/context_engine/sqlite_index.py`
- Test: `context-codebase/tests/test_sqlite_index.py`

### Step 1: 创建测试文件

```python
# context-codebase/tests/test_sqlite_index.py
import pytest
import tempfile
import os
from context_engine.sqlite_index import SQLiteIndex

class TestSQLiteIndex:
    def setup_method(self):
        """每个测试前创建临时数据库"""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.index = SQLiteIndex(self.db_path)
    
    def teardown_method(self):
        """清理临时文件"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_upsert_and_search(self):
        """插入后能搜索到"""
        chunks = [
            {
                "id": "test.py:1-10",
                "path": "test.py",
                "startLine": 1,
                "endLine": 10,
                "kind": "function",
                "name": "authenticate",
                "signals": ["auth", "login"],
                "preview": "def authenticate...",
                "language": "python"
            }
        ]
        
        self.index.upsert_chunks(chunks)
        results = self.index.search("auth")
        
        assert len(results) == 1
        assert results[0]["id"] == "test.py:1-10"
    
    def test_search_by_kind(self):
        """按 kind 搜索"""
        chunks = [
            {
                "id": "test.py:1-10",
                "path": "test.py",
                "startLine": 1,
                "endLine": 10,
                "kind": "function",
                "name": "foo",
                "signals": ["foo"],
                "preview": "...",
                "language": "python"
            },
            {
                "id": "test.py:12-20",
                "path": "test.py",
                "startLine": 12,
                "endLine": 20,
                "kind": "class",
                "name": "Bar",
                "signals": ["bar"],
                "preview": "...",
                "language": "python"
            }
        ]
        
        self.index.upsert_chunks(chunks)
        results = self.index.search("class:Bar")
        
        assert len(results) == 1
        assert results[0]["kind"] == "class"
    
    def test_delete_stale(self):
        """删除废弃 chunks"""
        chunks = [
            {
                "id": "test.py:1-10",
                "path": "test.py",
                "startLine": 1,
                "endLine": 10,
                "kind": "function",
                "name": "foo",
                "signals": [],
                "preview": "...",
                "language": "python"
            }
        ]
        
        self.index.upsert_chunks(chunks)
        self.index.delete_stale({"test.py:1-10"})
        
        # 再次插入空列表表示没有新的 valid ids
        self.index.upsert_chunks([])
        
        # 验证删除
        results = self.index.search("foo")
        assert len(results) == 0
```

### Step 2: 创建 SQLite 索引实现

```python
# context-codebase/scripts/context_engine/sqlite_index.py
"""
SQLite 索引 - 高速 KV 查询存储
"""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from typing import Optional

class SQLiteIndex:
    """基于 SQLite 的 chunk 索引"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """初始化数据库 schema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY,
                path TEXT NOT NULL,
                start_line INTEGER,
                end_line INTEGER,
                kind TEXT,
                name TEXT,
                language TEXT,
                content_hash TEXT,
                signals TEXT,
                preview TEXT
            )
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_path ON chunks(path)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_kind ON chunks(kind)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_language ON chunks(language)")
        
        conn.commit()
        conn.close()
    
    def upsert_chunks(self, chunks: list[dict]) -> None:
        """批量插入或更新 chunks"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        for chunk in chunks:
            signals_json = json.dumps(chunk.get("signals", []))
            
            cursor.execute("""
                INSERT OR REPLACE INTO chunks 
                (id, path, start_line, end_line, kind, name, language, signals, preview)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                chunk["id"],
                chunk["path"],
                chunk.get("startLine"),
                chunk.get("endLine"),
                chunk.get("kind"),
                chunk.get("name"),
                chunk.get("language"),
                signals_json,
                chunk.get("preview", "")[:200]
            ))
        
        conn.commit()
        conn.close()
    
    def search(self, query: str, limit: int = 10) -> list[dict]:
        """搜索 chunks"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 简单关键词匹配
        like_pattern = f"%{query}%"
        
        cursor.execute("""
            SELECT * FROM chunks 
            WHERE path LIKE ? OR signals LIKE ? OR preview LIKE ? OR name LIKE ?
            LIMIT ?
        """, (like_pattern, like_pattern, like_pattern, like_pattern, limit))
        
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
        
        conn.close()
        return results
    
    def get_by_path(self, path: str) -> list[dict]:
        """获取指定路径的所有 chunks"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM chunks WHERE path = ?", (path,))
        
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
        
        conn.close()
        return results
    
    def delete_stale(self, valid_ids: set[str]) -> None:
        """删除不在 valid_ids 中的 chunks"""
        if not valid_ids:
            return
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        placeholders = ','.join('?' * len(valid_ids))
        cursor.execute(f"DELETE FROM chunks WHERE id NOT IN ({placeholders})", tuple(valid_ids))
        
        conn.commit()
        conn.close()
    
    def close(self):
        """关闭连接"""
        # SQLite Python 自动管理连接，这里预留接口
        pass
```

### Step 3: 运行测试

```bash
cd /d/codes/context-codebase
python -m pytest context-codebase/tests/test_sqlite_index.py -v
```

### Step 4: 提交

```bash
git add context-codebase/scripts/context_engine/sqlite_index.py
git add context-codebase/tests/test_sqlite_index.py
git commit -m "feat: add SQLite index for fast KV queries"
```

---

## Task 4: 多语言分析器 (multi_lang_analyzer.py)

**Files:**
- Create: `context-codebase/scripts/context_engine/multi_lang_analyzer.py`
- Test: `context-codebase/tests/test_multi_lang_analyzer.py`

### Step 1: 创建测试文件

```python
# context-codebase/tests/test_multi_lang_analyzer.py
import pytest
from context_engine.multi_lang_analyzer import MultiLangAnalyzer

class TestMultiLangAnalyzer:
    def setup_method(self):
        self.analyzer = MultiLangAnalyzer()
    
    def test_supports_python(self):
        assert self.analyzer.supports(".py")
    
    def test_supports_typescript(self):
        assert self.analyzer.supports(".ts")
    
    def test_supports_go(self):
        assert self.analyzer.supports(".go")
    
    def test_supports_rust(self):
        assert self.analyzer.supports(".rs")
    
    def test_analyze_python(self):
        content = """
import fastapi

def hello():
    return {"message": "hello"}
"""
        result = self.analyzer.analyze(content, "test.py")
        
        assert result["language"] == "python"
        assert "fastapi" in result["imports"]
        assert "hello" in result["key_functions"]
    
    def test_analyze_go(self):
        content = """
package main

import "fmt"

func main() {
    fmt.Println("Hello")
}
"""
        result = self.analyzer.analyze(content, "test.go")
        
        assert result["language"] == "go"
        assert "fmt" in result["imports"]
    
    def test_analyze_rust(self):
        content = """
fn main() {
    println!("Hello, world!");
}
"""
        result = self.analyzer.analyze(content, "test.rs")
        
        assert result["language"] == "rust"
        assert "main" in result["key_functions"]
```

### Step 2: 创建多语言分析器实现

```python
# context-codebase/scripts/context_engine/multi_lang_analyzer.py
"""
多语言分析器 - 全语言支持
"""
from __future__ import annotations
import ast
import re
from pathlib import Path
from typing import Optional

class MultiLangAnalyzer:
    """支持多语言的分析器"""
    
    EXT_TO_LANGUAGE = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".go": "go",
        ".rs": "rust",
        ".java": "java",
        ".cs": "csharp",
        ".php": "php",
        ".rb": "ruby",
        ".c": "cpp",
        ".cpp": "cpp",
        ".cc": "cpp",
        ".cxx": "cpp",
        ".h": "cpp",
        ".hpp": "cpp",
    }
    
    def supports(self, ext: str) -> bool:
        """是否支持该扩展名"""
        return ext.lower() in self.EXT_TO_LANGUAGE
    
    def analyze(self, content: str, filepath: str) -> dict:
        """分析文件内容"""
        ext = Path(filepath).suffix.lower()
        language = self.EXT_TO_LANGUAGE.get(ext, "unknown")
        
        if language == "python":
            return self._analyze_python(content, filepath)
        elif language == "go":
            return self._analyze_go(content, filepath)
        elif language == "rust":
            return self._analyze_rust(content, filepath)
        elif language in ("javascript", "typescript"):
            return self._analyze_js(content, filepath)
        else:
            return self._fallback_analysis(content, filepath, language)
    
    def _analyze_python(self, content: str, filepath: str) -> dict:
        """分析 Python 文件"""
        result = self._base_analysis(content, filepath)
        result["language"] = "python"
        
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        result["imports"].append(alias.name.split('.')[0])
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        result["imports"].append(node.module.split('.')[0])
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not node.name.startswith('_'):
                        result["key_functions"].append(node.name)
                elif isinstance(node, ast.ClassDef):
                    if not node.name.startswith('_'):
                        result["exports"].append(node.name)
        except SyntaxError:
            pass
        
        return result
    
    def _analyze_go(self, content: str, filepath: str) -> dict:
        """分析 Go 文件"""
        result = self._base_analysis(content, filepath)
        result["language"] = "go"
        
        # import "fmt"
        for match in re.finditer(r'import\s+"([^"]+)"', content):
            result["imports"].append(match.group(1))
        
        # import (
        #     "fmt"
        # )
        for match in re.finditer(r'import\s*\(([^)]+)\)', content, re.DOTALL):
            for imp in re.finditer(r'"([^"]+)"', match.group(1)):
                result["imports"].append(imp.group(1))
        
        # func main()
        for match in re.finditer(r'func\s+(\w+)\s*\(', content):
            result["key_functions"].append(match.group(1))
        
        # func (t *T) Method()
        for match in re.finditer(r'func\s+\([^)]+\)\s+(\w+)\s*\(', content):
            if match.group(1) not in result["key_functions"]:
                result["key_functions"].append(match.group(1))
        
        return result
    
    def _analyze_rust(self, content: str, filepath: str) -> dict:
        """分析 Rust 文件"""
        result = self._base_analysis(content, filepath)
        result["language"] = "rust"
        
        # use crate::module;
        for match in re.finditer(r'use\s+([^;]+);', content):
            result["imports"].append(match.group(1).split("::")[0])
        
        # fn function_name()
        for match in re.finditer(r'fn\s+(\w+)\s*[\(<]', content):
            name = match.group(1)
            if not name.startswith('_'):
                result["key_functions"].append(name)
        
        # struct, enum, trait
        for match in re.finditer(r'(struct|enum|trait)\s+(\w+)', content):
            result["exports"].append(match.group(2))
        
        return result
    
    def _analyze_js(self, content: str, filepath: str) -> dict:
        """分析 JavaScript/TypeScript 文件"""
        result = self._base_analysis(content, filepath)
        result["language"] = "javascript" if ".js" in filepath else "typescript"
        
        # import xxx from 'yyy'
        for match in re.finditer(r"import\s+(?:{\s*)?(\w+)(?:\s*,)?\s*.*?\s+from\s+['\"]([^'\"]+)['\"]", content):
            result["imports"].append(match.group(2).split('/')[0])
            if match.group(1):
                result["exports"].append(match.group(1))
        
        # require('xxx')
        for match in re.finditer(r"require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", content):
            result["imports"].append(match.group(1).split('/')[0])
        
        # export function / export const
        for match in re.finditer(r'export\s+(?:function|const|let|var|class)\s+(\w+)', content):
            result["exports"].append(match.group(1))
        
        # function name()
        for match in re.finditer(r'(?:^|\n)function\s+(\w+)\s*\(', content, re.MULTILINE):
            if match.group(1) not in result["exports"]:
                result["key_functions"].append(match.group(1))
        
        return result
    
    def _fallback_analysis(self, content: str, filepath: str, language: str) -> dict:
        """通用 fallback 分析"""
        result = self._base_analysis(content, filepath)
        result["language"] = language
        return result
    
    def _base_analysis(self, content: str, filepath: str) -> dict:
        """基础分析结构"""
        return {
            "path": filepath,
            "imports": [],
            "exports": [],
            "api_routes": [],
            "data_models": [],
            "key_functions": [],
            "framework_hints": [],
            "language": "unknown"
        }
```

### Step 3: 运行测试

```bash
cd /d/codes/context-codebase
python -m pytest context-codebase/tests/test_multi_lang_analyzer.py -v
```

### Step 4: 提交

```bash
git add context-codebase/scripts/context_engine/multi_lang_analyzer.py
git add context-codebase/tests/test_multi_lang_analyzer.py
git commit -m "feat: add multi-language analyzer support"
```

---

## Task 5: 集成到 generate.py

**Files:**
- Modify: `context-codebase/scripts/generate.py`

### Step 1: 读取当前 generate.py 的相关部分

```python
# 找到以下位置并修改：
# 1. 导入部分 - 添加新模块
# 2. chunk 生成部分 - 使用 SemanticChunker
# 3. 增量逻辑 - 使用 ChunkTracker
# 4. 索引存储 - 使用 SQLiteIndex
```

### Step 2: 添加导入

```python
# 在 generate.py 开头添加：
from context_engine.semantic_chunker import SemanticChunker
from context_engine.chunk_tracker import ChunkTracker
from context_engine.sqlite_index import SQLiteIndex
from context_engine.multi_lang_analyzer import MultiLangAnalyzer
```

### Step 3: 添加 Flag 解析

```python
# 在 main() 函数或 ArgumentParser 部分添加：
parser.add_argument('--semantic', action='store_true', help='启用语义分块')
parser.add_argument('--incremental', action='store_true', help='启用增量模式')
parser.add_argument('--sqlite', action='store_true', help='使用 SQLite 索引')
```

### Step 4: 修改 chunk 生成逻辑

```python
# 找到 _build_chunks 或类似函数，修改为：
def _build_chunks(self, files: list[dict], use_semantic: bool = False) -> list[dict]:
    """构建 chunks，支持语义分块"""
    if not use_semantic:
        # 原有固定分块逻辑
        return self._chunk_by_lines(files)
    
    # 语义分块
    chunker = SemanticChunker()
    analyzer = MultiLangAnalyzer()
    all_chunks = []
    
    for file_record in files:
        content = file_record.get("content", "")
        path = file_record["path"]
        ext = Path(path).suffix.lower()
        
        if analyzer.supports(ext):
            lang = analyzer.EXT_TO_LANGUAGE.get(ext, "unknown")
            chunks = chunker.chunk_file(content, path, lang)
            all_chunks.extend(chunks)
        else:
            # 不支持的语言，使用简单分块
            all_chunks.extend(self._simple_chunk(content, path))
    
    return all_chunks
```

### Step 5: 添加增量更新逻辑

```python
# 找到 _update_incremental 或类似函数：
def _update_incremental(self, new_chunks: list[dict], db_path: str) -> dict:
    """增量更新索引"""
    tracker = ChunkTracker()
    index = SQLiteIndex(db_path)
    
    # 加载旧的 chunk states
    old_states = self._load_chunk_states(db_path)
    
    # 追踪新的 chunks
    new_states = tracker.track(new_chunks)
    
    # 计算 diff
    diff = tracker.diff(old_states, new_states)
    
    # 应用变更
    if diff.added:
        index.upsert_chunks(diff.added)
    if diff.modified:
        index.upsert_chunks(diff.modified)
    if diff.deleted:
        valid_ids = set(new_states.keys())
        index.delete_stale(valid_ids)
    
    # 合并状态
    merged = tracker.merge_states(old_states, new_states)
    self._save_chunk_states(merged, db_path)
    
    return {"added": len(diff.added), "modified": len(diff.modified), "deleted": len(diff.deleted)}
```

### Step 6: 提交

```bash
git add context-codebase/scripts/generate.py
git commit -m "feat: integrate semantic chunker, chunk tracker, and SQLite index"
```

---

## 执行方式

**Plan complete and saved to `docs/plans/2026-04-01-context-codebase-enhancement-implementation-plan.md`**

**Two execution options:**

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

**Which approach?**
