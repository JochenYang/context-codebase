# context-codebase 增强设计方案

**日期**: 2026-04-01
**版本**: 1.0
**状态**: 已批准

---

## 一、目标

在不破坏现有架构的前提下，通过模块化增强实现：

1. **语义分块** — 基于 AST 边界的智能分块，替代固定 60 行
2. **Chunk 级增量追踪** — 精准检测代码变更影响范围
3. **SQLite 索引存储** — 高速 KV 查询，保留 JSON 人类可读性
4. **全语言支持** — Python/JS/TS/Go/Rust/Java/C# /PHP/Ruby/C++ 等

---

## 二、核心架构

```
┌─────────────────────────────────────────────────────────┐
│                    Skill Layer                           │
│            /context-codebase (SKILL.md)                  │
└─────────────────────┬───────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────┐
│                   Script Layer                          │
│  generate.py ──── enhanced ──── generate.py             │
│         │                                       │       │
│         └──►  context_engine/                     │◄─┘   │
│              │  analyzers.py       (增强)        │       │
│              │  graph.py          (增强)        │       │
│              │  retrieval.py      (增强)        │       │
│              │  csr.py            (保留)        │       │
│              │  external_context.py (保留)       │       │
│              │                                   │       │
│              │  [NEW] semantic_chunker.py       │       │
│              │  [NEW] chunk_tracker.py          │       │
│              │  [NEW] sqlite_index.py           │       │
│              │  [NEW] multi_lang_analyzer.py    │       │
│              └─────────────────────────────────┘       │
└─────────────────────────────────────────────────────────┘
```

---

## 三、模块详细设计

### 3.1 语义分块器 (semantic_chunker.py)

**目标**: 基于 AST 边界做智能分块，保持函数/类完整性

**分块策略**:

| 文件大小 | 策略 |
|----------|------|
| < 60 行 | 保持原样，整块 |
| 60-150 行 | 按函数/类边界分 |
| > 150 行 | 按函数边界 + 段落拆分 |

**接口设计**:

```python
class SemanticChunker:
    def chunk_file(self, content: str, filepath: str, ast_tree) -> list[dict]:
        """
        Returns list of chunks:
        {
            "id": "path:start-end",
            "path": str,
            "startLine": int,
            "endLine": int,
            "kind": "function|class|section",
            "name": str,
            "signals": list[str],  # 语义关键词
            "content": str,
            "preview": str,
        }
        """
        pass
```

### 3.2 Chunk 追踪器 (chunk_tracker.py)

**目标**: 记录每个 chunk 的版本和变更历史

**接口设计**:

```python
@dataclass
class ChunkState:
    chunk_id: str
    content_hash: str
    version: int

@dataclass
class ChangeSet:
    added: list[dict]      # 新 chunk
    modified: list[dict]   # 变更 chunk
    deleted: list[str]     # 删除的 chunk_id
    unchanged: list[str]   # 未变更的 chunk_id

class ChunkTracker:
    def track(self, chunks: list[dict]) -> dict[str, ChunkState]:
        """为每个 chunk 生成稳定 ID 和状态"""
        pass

    def diff(self, old: dict[str, ChunkState], new: dict[str, ChunkState]) -> ChangeSet:
        """比对变更集"""
        pass
```

**Chunk ID 生成规则**: `{path}:{start_line}-{end_line}`

### 3.3 SQLite 索引 (sqlite_index.py)

**目标**: 高速 KV 查询，替代 JSON 文件顺序扫描

**数据库 Schema**:

```sql
CREATE TABLE chunks (
    id TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    start_line INTEGER,
    end_line INTEGER,
    kind TEXT,
    language TEXT,
    content_hash TEXT,
    signals TEXT,  -- JSON array
    preview TEXT
);

CREATE INDEX idx_path ON chunks(path);
CREATE INDEX idx_kind ON chunks(kind);
CREATE INDEX idx_language ON chunks(language);

CREATE VIRTUAL TABLE chunks_fts USING fts5(
    path, signals, preview,
    content='chunks'
);
```

**接口设计**:

```python
class SQLiteIndex:
    def upsert_chunks(self, chunks: list[dict]) -> None:
        """批量插入或更新 chunks"""
        pass

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """全文检索"""
        pass

    def get_by_path(self, path: str) -> list[dict]:
        """获取路径下的所有 chunks"""
        pass

    def delete_stale(self, valid_ids: set[str]) -> None:
        """删除废弃 chunks"""
        pass
```

### 3.4 多语言分析器 (multi_lang_analyzer.py)

**目标**: 全语言支持

| 语言 | 分析器 | AST 依赖 |
|------|--------|----------|
| Python | PythonAstAnalyzer | 内置 ast |
| JS/TS | TypeScriptAnalyzer | node (可选) |
| Go | GoAstAnalyzer | go/parser |
| Rust | RustAnalyzer | tree-sitter |
| Java | JavaAnalyzer | javalang 或正则 |
| C# | CSharpAnalyzer | 正则 fallback |
| PHP | PHPAnalyzer | 正则 |
| Ruby | RubyAnalyzer | 正则 |
| C/C++ | CppAnalyzer | tree-sitter |

**接口设计**:

```python
class MultiLangAnalyzer:
    def analyze(self, content: str, filepath: str) -> FileAnalysis:
        """
        统一接口，返回:
        {
            "imports": list[str],
            "exports": list[str],
            "api_routes": list[dict],
            "data_models": list[dict],
            "key_functions": list[dict],
            "framework_hints": list[str],
            "language": str
        }
        """
        pass

    def supports(self, ext: str) -> bool:
        """是否支持该扩展名"""
        pass
```

---

## 四、检索增强

### 4.1 混合检索策略

```python
class EnhancedRetrieval:
    """
    检索_pipeline:
    1. SQLite FTS5 关键词检索
    2. AST 感知扩展 (import 图)
    3. 重要性加权 (important_files)
    4. 增量变更加权 (recent_changed)
    5. 语义信号匹配 (signals)
    """

    def retrieve(self, query: str, task: str, context: dict) -> list[dict]:
        pass
```

### 4.2 signals 信号系统

每个 chunk 携带语义信号，用于语义匹配：

```python
{
    "id": "src/services/auth.py:42-78",
    "signals": ["authentication", "jwt", "session", "middleware"],
    "kind": "function",
    "name": "validate_token",
    "language": "python"
}
```

---

## 五、向后兼容

**Flag 机制**:

```bash
# 基础模式（向后兼容）
python generate.py /path/to/project

# 增强模式（语义分块 + SQLite）
python generate.py /path/to/project --semantic

# 增量模式
python generate.py /path/to/project refresh --incremental

# 组合模式
python generate.py /path/to/project --semantic --incremental
```

**环境变量**:

```bash
export CONTEXT_CODEBASE_SEMANTIC=1
export CONTEXT_CODEBASE_SQLITE=1
export CONTEXT_CODEBASE_LANGUAGE=go,rust
```

---

## 六、数据流

```
generate.py [refresh]
    │
    ├─► ChunkTracker.track()
    │       │  比对旧 chunk 状态
    │       ▼
    │   ChangeSet {added, modified, deleted}
    │
    ├─► [增量模式]
    │       │  只处理 changed chunks
    │       ▼
    │   SemanticChunker.chunk_file()  (仅变更文件)
    │
    ├─► [全量模式]
    │       ▼
    │   SemanticChunker.chunk_file()  (所有文件)
    │
    ▼
SQLiteIndex.upsert_chunks()
    │
    ▼
snapshot.json (完整快照)
    │
    ▼
context_packs (task-specific retrieval)
```

---

## 七、测试策略

```
tests/
├── test_semantic_chunker.py     # AST 分块正确性
├── test_chunk_tracker.py         # 增量检测准确性
├── test_sqlite_index.py         # 查询性能
├── test_multi_lang_analyzer.py   # 各语言分析
└── test_retrieval.py            # 检索质量
```

---

## 八、实现顺序

1. **semantic_chunker.py** — 核心，依赖最少
2. **chunk_tracker.py** — 依赖 semantic_chunker
3. **sqlite_index.py** — 依赖 chunk_tracker
4. **multi_lang_analyzer.py** — 可独立测试
5. **analyzers.py 增强** — 集成多语言
6. **retrieval.py 增强** — 集成 signals
7. **generate.py 集成** — 组装所有模块

---

## 九、风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| AST 分析性能 | 增量模式避免全量解析 |
| SQLite 兼容性 | JSON 快照保留导出能力 |
| 多语言正则 fallback 准确性 | 明确 confidence 标记 |
| 破坏现有工作流 | Flag 机制，默认向后兼容 |
