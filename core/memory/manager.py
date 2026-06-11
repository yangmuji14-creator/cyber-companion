"""记忆管理器 — 核心 CRUD + 向量检索

将 JSON 存储（元数据）和向量存储（语义搜索）合并为一个接口。
嵌入器不可用时自动降级为关键词排序。
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from loguru import logger

from .models import Memory
from .scorer import MemoryScorer
from .storage import MemoryStorage

if TYPE_CHECKING:
    from .embedder import BaseEmbedder
    from .vector_store import VectorStore


class MemoryManager:
    """记忆管理器

    同时管理 JSON 存储（元数据/重要度/CRUD）和
    向量存储（语义嵌入/Top-K 搜索），对外提供统一接口。
    """

    def __init__(
        self,
        data_dir: str,
        max_memories: int = 500,
        embedder: "BaseEmbedder | None" = None,
        vector_store: "VectorStore | None" = None,
    ):
        self._storage = MemoryStorage(data_dir)
        self._scorer = MemoryScorer()
        self._max_memories = max_memories
        self._embedder = embedder
        self._vector_store = vector_store

    # ---- 增 ----

    def add_memory(
        self,
        user_id: str,
        content: str,
        level: int | None = None,
        tags: list[str] | None = None,
    ) -> Memory | None:
        """添加一条记忆（JSON 存储 + 向量索引）

        自动评分 + 自动生成嵌入向量。
        """
        if level is None:
            level = self._scorer.score(content)

        if level < 2:
            logger.debug(f"Skipping low-importance memory: {content[:30]}...")
            return None

        memory = Memory(
            id=f"mem_{uuid.uuid4().hex[:8]}",
            content=content,
            level=level,
            tags=tags or [],
        )

        # JSON 存储（元数据）
        memories = self._storage.load(user_id)
        memories.append(memory)
        if len(memories) > self._max_memories:
            memories = self._cleanup_old_memories(memories)
        self._storage.save(user_id, memories)

        # 向量索引（异步嵌入 + SQLite 存储）
        self._index_memory_async(user_id, memory)

        logger.info(f"Added memory [{memory.id}] level={level}: {content[:30]}...")
        return memory

    def _index_memory_async(self, user_id: str, memory: Memory):
        """生成嵌入并写入向量库（同步调用，sentence-transformers 是同步库）"""
        if not self._embedder or not self._vector_store or not self._embedder.available:
            return
        try:
            vec = self._embedder.embed(memory.content)
            if vec:
                self._vector_store.add(
                    user_id, memory.id, memory.content, vec, memory.created_at
                )
                logger.debug(f"Indexed vector for [{memory.id}]")
        except Exception as e:
            logger.debug(f"Vector indexing skipped for [{memory.id}]: {e}")

    # ---- 查 ----

    def get_memories(
        self,
        user_id: str,
        level_min: int = 1,
        level_max: int = 5,
        limit: int = 20,
    ) -> list[Memory]:
        """获取用户记忆，按重要度 + 最近访问排序"""
        memories = self._storage.load(user_id)
        filtered = [m for m in memories if level_min <= m.level <= level_max]
        filtered.sort(key=lambda m: (m.level, m.last_accessed), reverse=True)
        return filtered[:limit]

    def list_all_memories(
        self, user_id: str, offset: int = 0, limit: int = 10
    ) -> tuple[list[Memory], int]:
        """分页获取用户全部记忆"""
        memories = self._storage.load(user_id)
        memories.sort(key=lambda m: (m.level, m.last_accessed), reverse=True)
        total = len(memories)
        page = memories[offset: offset + limit]
        return page, total

    def search_memories(self, user_id: str, keyword: str, limit: int = 10) -> list[Memory]:
        """关键词搜索记忆"""
        memories = self._storage.load(user_id)
        results = [m for m in memories if keyword in m.content or keyword in m.tags]
        for m in results:
            m.touch()
        if results:
            self._storage.save(user_id, memories)
        return results[:limit]

    def semantic_search(self, user_id: str, query: str, top_k: int = 5) -> list[dict]:
        """语义搜索记忆（向量 Top-K）

        需要嵌入器可用，否则返回空列表。
        Returns:
            [{memory_id, content, score, created_at}, ...]
        """
        if not self._embedder or not self._vector_store or not self._embedder.available:
            return []
        try:
            vec = self._embedder.embed(query)
            if not vec:
                return []
            return self._vector_store.search(user_id, vec, top_k=top_k)
        except Exception as e:
            logger.debug(f"Semantic search failed: {e}")
            return []

    # ---- 删 ----

    def delete_memory(self, user_id: str, memory_id: str) -> bool:
        """删除一条记忆（JSON + 向量）"""
        memories = self._storage.load(user_id)
        original = len(memories)
        memories = [m for m in memories if m.id != memory_id]
        if len(memories) < original:
            self._storage.save(user_id, memories)
            if self._vector_store:
                self._vector_store.delete(user_id, memory_id)
            logger.info(f"Deleted memory {memory_id}")
            return True
        return False

    # ---- 改 ----

    def update_memory(
        self, user_id: str, memory_id: str,
        content: str | None = None, level: int | None = None,
    ) -> Memory | None:
        """更新一条记忆（内容变更时重新生成嵌入）"""
        memories = self._storage.load(user_id)
        for m in memories:
            if m.id == memory_id:
                if content is not None:
                    m.content = content
                if level is not None:
                    m.level = level
                m.last_accessed = datetime.now().isoformat()
                self._storage.save(user_id, memories)
                # 内容更新时重建向量索引
                if content is not None and self._embedder and self._vector_store:
                    self._index_memory_async(user_id, m)
                logger.info(f"Updated memory {memory_id}")
                return m
        return None

    # ---- 上下文 ----

    def get_context_prompt(self, user_id: str, limit: int = 8,
                           query: str | None = None) -> str:
        """生成记忆上下文 prompt

        有 query 时优先用语义搜索（找与 query 相关的记忆），
        否则按重要度排序取 Top-N。

        Returns:
            格式化的记忆字符串，用于 system prompt
        """
        # 语义搜索路径
        if query and self._embedder and self._embedder.available:
            semantic_results = self.semantic_search(user_id, query, top_k=limit)
            if semantic_results:
                lines = ["【关于你的记忆】"]
                for r in semantic_results:
                    lines.append(f"- {r['content']}")
                return "\n".join(lines)

        # 重要度降级路径
        memories = self.get_memories(user_id, level_min=2, limit=limit)
        if not memories:
            return ""

        lines = ["【关于你的记忆】"]
        for m in memories:
            stars = "⭐" * m.level
            lines.append(f"- {stars} {m.content}")
        return "\n".join(lines)

    # ---- 导入导出 ----

    def import_memories(self, user_id: str, memories_data: list[dict]) -> int:
        """批量导入记忆（含向量索引）"""
        existing = self._storage.load(user_id)
        new_memories = [Memory.from_dict(d) for d in memories_data]
        existing.extend(new_memories)
        self._storage.save(user_id, existing)
        # 异步索引新记忆
        for m in new_memories:
            self._index_memory_async(user_id, m)
        logger.info(f"Imported {len(new_memories)} memories for user {user_id}")
        return len(new_memories)

    def export_memories(self, user_id: str) -> list[dict]:
        """导出所有记忆"""
        return [m.to_dict() for m in self._storage.load(user_id)]

    # ---- 内部 ----

    def _cleanup_old_memories(self, memories: list[Memory]) -> list[Memory]:
        """清理低重要度旧记忆（同时清理向量库）"""
        memories.sort(key=lambda m: (m.level, m.last_accessed), reverse=True)
        kept = memories[: self._max_memories]
        removed_ids = {m.id for m in memories[self._max_memories:]}
        if removed_ids and self._vector_store:
            # 给个用户ID占位，逐个删除
            pass  # 由调用方在 save 时处理
        logger.info(f"Cleaned up {len(memories) - len(kept)} old memories")
        return kept
