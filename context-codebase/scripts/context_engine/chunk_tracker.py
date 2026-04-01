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