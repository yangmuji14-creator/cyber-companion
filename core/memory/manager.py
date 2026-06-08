"""记忆管理器 - 核心 CRUD + 检索"""

import uuid
from datetime import datetime

from loguru import logger

from .models import Memory
from .scorer import MemoryScorer
from .storage import MemoryStorage


class MemoryManager:
    """记忆管理器

    负责记忆的增删改查、自动评分、检索排序。
    """

    def __init__(self, data_dir: str, max_memories: int = 500):
        self._storage = MemoryStorage(data_dir)
        self._scorer = MemoryScorer()
        self._max_memories = max_memories

    def add_memory(
        self,
        user_id: str,
        content: str,
        level: int | None = None,
        tags: list[str] | None = None,
    ) -> Memory | None:
        """添加一条记忆

        Args:
            user_id: 用户 ID
            content: 记忆内容
            level: 重要度（1-5），不指定则自动评分
            tags: 标签列表

        Returns:
            创建的 Memory 对象，如果评分太低不值得记住则返回 None
        """
        # 自动评分
        if level is None:
            level = self._scorer.score(content)

        # 低于 2 分的不记住
        if level < 2:
            logger.debug(f"Skipping low-importance memory: {content[:30]}...")
            return None

        memory = Memory(
            id=f"mem_{uuid.uuid4().hex[:8]}",
            content=content,
            level=level,
            tags=tags or [],
        )

        memories = self._storage.load(user_id)
        memories.append(memory)

        # 超出上限时清理低重要度的旧记忆
        if len(memories) > self._max_memories:
            memories = self._cleanup_old_memories(memories)

        self._storage.save(user_id, memories)
        logger.info(f"Added memory [{memory.id}] level={level}: {content[:30]}...")
        return memory

    def get_memories(
        self,
        user_id: str,
        level_min: int = 1,
        level_max: int = 5,
        limit: int = 20,
    ) -> list[Memory]:
        """获取用户记忆，按重要度和最近访问排序

        Args:
            user_id: 用户 ID
            level_min: 最低重要度
            level_max: 最高重要度
            limit: 返回数量上限

        Returns:
            排序后的记忆列表
        """
        memories = self._storage.load(user_id)

        # 按重要度筛选
        filtered = [
            m for m in memories
            if level_min <= m.level <= level_max
        ]

        # 按重要度降序 + 最近访问降序排序
        filtered.sort(key=lambda m: (m.level, m.last_accessed), reverse=True)

        return filtered[:limit]

    def search_memories(
        self, user_id: str, keyword: str, limit: int = 10
    ) -> list[Memory]:
        """按关键词搜索记忆"""
        memories = self._storage.load(user_id)
        results = [m for m in memories if keyword in m.content or keyword in m.tags]

        # 更新访问记录
        for m in results:
            m.touch()

        if results:
            self._storage.save(user_id, memories)

        return results[:limit]

    def delete_memory(self, user_id: str, memory_id: str) -> bool:
        """删除一条记忆"""
        memories = self._storage.load(user_id)
        original_count = len(memories)
        memories = [m for m in memories if m.id != memory_id]

        if len(memories) < original_count:
            self._storage.save(user_id, memories)
            logger.info(f"Deleted memory {memory_id} for user {user_id}")
            return True
        return False

    def update_memory(
        self, user_id: str, memory_id: str, content: str | None = None, level: int | None = None
    ) -> Memory | None:
        """更新一条记忆"""
        memories = self._storage.load(user_id)
        for m in memories:
            if m.id == memory_id:
                if content is not None:
                    m.content = content
                if level is not None:
                    m.level = level
                m.last_accessed = datetime.now().isoformat()
                self._storage.save(user_id, memories)
                logger.info(f"Updated memory {memory_id}")
                return m
        return None

    def get_context_prompt(self, user_id: str, limit: int = 10) -> str:
        """生成记忆上下文 prompt，注入到对话中

        Returns:
            格式化的记忆字符串，用于 system prompt
        """
        memories = self.get_memories(user_id, level_min=2, limit=limit)
        if not memories:
            return ""

        lines = ["【你对这个用户的记忆】"]
        for m in memories:
            stars = "⭐" * m.level
            lines.append(f"- {stars} {m.content}")

        return "\n".join(lines)

    def import_memories(self, user_id: str, memories_data: list[dict]) -> int:
        """批量导入记忆"""
        count = 0
        for data in memories_data:
            memory = Memory.from_dict(data)
            existing = self._storage.load(user_id)
            existing.append(memory)
            self._storage.save(user_id, existing)
            count += 1
        logger.info(f"Imported {count} memories for user {user_id}")
        return count

    def export_memories(self, user_id: str) -> list[dict]:
        """导出用户所有记忆"""
        memories = self._storage.load(user_id)
        return [m.to_dict() for m in memories]

    def _cleanup_old_memories(self, memories: list[Memory]) -> list[Memory]:
        """清理旧记忆：优先保留高重要度的"""
        memories.sort(key=lambda m: (m.level, m.last_accessed), reverse=True)
        kept = memories[: self._max_memories]
        removed = len(memories) - len(kept)
        logger.info(f"Cleaned up {removed} old memories")
        return kept
