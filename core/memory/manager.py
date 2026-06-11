"""记忆管理器 - 核心 CRUD + 智能检索 + 冲突检测

集成双层评分（规则 + LLM）、结构化分类、记忆冲突检测与更新。
"""

import uuid
from datetime import datetime

from loguru import logger

from .models import Memory, MemoryCategory
from .scorer import MemoryScorer, LLMMemoryScorer
from .storage import MemoryStorage


class MemoryManager:
    """记忆管理器

    负责记忆的增删改查、智能评分、检索排序、冲突检测。
    """

    def __init__(self, data_dir: str, max_memories: int = 500, llm=None):
        self._storage = MemoryStorage(data_dir)
        self._scorer = MemoryScorer()
        self._llm_scorer = LLMMemoryScorer(llm)
        self._max_memories = max_memories

    def set_llm(self, llm) -> None:
        """延迟设置 LLM（用于首次对话时初始化）"""
        self._llm_scorer._llm = llm

    async def add_memory(
        self,
        user_id: str,
        content: str,
        level: int | None = None,
        tags: list[str] | None = None,
        category: str | None = None,
        source: str = "auto",
    ) -> Memory | None:
        """添加一条记忆（支持 LLM 辅助评分和自动分类）

        Args:
            user_id: 用户 ID
            content: 记忆内容
            level: 重要度（1-5），不指定则自动评分
            tags: 标签列表
            category: 记忆分类，不指定则自动分类
            source: 来源标识

        Returns:
            创建的 Memory 对象，如果评分太低不值得记住则返回 None
        """
        if level is None:
            # 双层评分：先用规则评分
            level, confidence = self._scorer.score(content)

            # 低置信度时用 LLM 二次评估
            if self._scorer.needs_llm_evaluation(content) and self._llm_scorer._llm:
                llm_result = await self._llm_scorer.evaluate(content)
                if llm_result:
                    llm_level, llm_category = llm_result
                    level = llm_level
                    if category is None:
                        category = llm_category
                    logger.debug(
                        f"LLM overrode score: {level} for '{content[:30]}...'"
                    )

        # 低于 2 分的不记住
        if level < 2:
            logger.debug(f"Skipping low-importance memory: {content[:30]}...")
            return None

        # 自动分类
        if category is None:
            category = Memory.classify(content)

        memory = Memory(
            id=f"mem_{uuid.uuid4().hex[:8]}",
            content=content,
            level=level,
            category=category,
            tags=tags or [],
            source=source,
        )

        memories = self._storage.load(user_id)

        # 冲突检测：检查是否有矛盾的旧记忆需要更新
        conflict = self._detect_conflict(memory, memories)
        if conflict:
            conflict.superseded_by = memory.id
            memory.related_memory_ids = [conflict.id]
            logger.info(
                f"Memory conflict: '{conflict.content[:30]}' "
                f"superseded by '{memory.content[:30]}'"
            )

        memories.append(memory)

        # 超出上限时清理低重要度的旧记忆（跳过未被取代的）
        if len(memories) > self._max_memories:
            memories = self._cleanup_old_memories(memories)

        self._storage.save(user_id, memories)
        logger.info(
            f"Added memory [{memory.id}] level={level} cat={category}: "
            f"{content[:30]}..."
        )
        return memory

    def add_memory_sync(
        self,
        user_id: str,
        content: str,
        level: int | None = None,
        tags: list[str] | None = None,
        category: str | None = None,
        source: str = "auto",
    ) -> Memory | None:
        """同步版本的 add_memory（仅使用规则评分，不调用 LLM）

        用于不能 async 的场景或不需要 LLM 评分时。
        """
        if level is None:
            level, _ = self._scorer.score(content)

        if level < 2:
            logger.debug(f"Skipping low-importance memory: {content[:30]}...")
            return None

        if category is None:
            category = Memory.classify(content)

        memory = Memory(
            id=f"mem_{uuid.uuid4().hex[:8]}",
            content=content,
            level=level,
            category=category,
            tags=tags or [],
            source=source,
        )

        memories = self._storage.load(user_id)

        conflict = self._detect_conflict(memory, memories)
        if conflict:
            conflict.superseded_by = memory.id
            memory.related_memory_ids = [conflict.id]
            logger.info(
                f"Memory conflict: '{conflict.content[:30]}' "
                f"superseded by '{memory.content[:30]}'"
            )

        memories.append(memory)

        if len(memories) > self._max_memories:
            memories = self._cleanup_old_memories(memories)

        self._storage.save(user_id, memories)
        logger.info(
            f"Added memory [{memory.id}] level={level} cat={category}: "
            f"{content[:30]}..."
        )
        return memory

    def _detect_conflict(
        self, new_memory: Memory, existing: list[Memory]
    ) -> Memory | None:
        """检测新记忆与已有记忆的冲突

        冲突条件：
        1. 同分类（如都是 preference）
        2. 内容涉及同一主题（关键词重叠）
        3. 语义相反（喜欢 vs 讨厌、养 vs 不养）

        Returns:
            冲突的旧记忆，无冲突返回 None
        """
        content = new_memory.content

        # 反义词对
        antonym_pairs = [
            ("喜欢", "讨厌"), ("爱", "恨"), ("开心", "难过"),
            ("养", "不养"), ("有", "没有"), ("是", "不是"),
            ("会", "不会"), ("想", "不想"), ("去", "不去"),
        ]

        for mem in existing:
            if mem.is_superseded:
                continue

            # 只检查同分类
            if mem.category != new_memory.category:
                continue

            # 检查关键词重叠（至少 2 个共同关键词）
            mem_keywords = set(mem.content)
            new_keywords = set(content)
            overlap = len(mem_keywords & new_keywords)
            if overlap < 4:  # 至少 4 个字符重叠（中文）
                continue

            # 检查反义词对
            for pos, neg in antonym_pairs:
                if (pos in content and neg in mem.content) or \
                   (neg in content and pos in mem.content):
                    return mem

            # 同一主体不同信息（如"我叫小明" vs "我叫小红"）
            if new_memory.category == "personal":
                # 都包含"我叫"或"我是"但名字不同
                if ("叫" in content and "叫" in mem.content) or \
                   ("是" in content and "是" in mem.content):
                    if content != mem.content:
                        return mem

        return None

    def get_memories(
        self,
        user_id: str,
        level_min: int = 1,
        level_max: int = 5,
        limit: int = 20,
        category: str | None = None,
        include_superseded: bool = False,
    ) -> list[Memory]:
        """获取用户记忆，按重要度和最近访问排序

        Args:
            user_id: 用户 ID
            level_min: 最低重要度
            level_max: 最高重要度
            limit: 返回数量上限
            category: 按分类筛选
            include_superseded: 是否包含已被取代的记忆

        Returns:
            排序后的记忆列表
        """
        memories = self._storage.load(user_id)

        # 过滤
        filtered = []
        for m in memories:
            if not include_superseded and m.is_superseded:
                continue
            if not (level_min <= m.level <= level_max):
                continue
            if category and m.category != category:
                continue
            filtered.append(m)

        # 按重要度降序 + 最近访问降序排序
        filtered.sort(key=lambda m: (m.level, m.last_accessed), reverse=True)

        return filtered[:limit]

    def list_all_memories(
        self,
        user_id: str,
        offset: int = 0,
        limit: int = 10,
    ) -> tuple[list[Memory], int]:
        """分页获取用户全部记忆（不含已被取代的）

        Args:
            user_id: 用户 ID
            offset: 跳过前 N 条
            limit: 每页数量

        Returns:
            (当前页记忆列表, 总数) 元组
        """
        memories = self._storage.load(user_id)
        active = [m for m in memories if not m.is_superseded]
        active.sort(key=lambda m: (m.level, m.last_accessed), reverse=True)
        total = len(active)
        page = active[offset: offset + limit]
        return page, total

    def search_memories(
        self, user_id: str, keyword: str, limit: int = 10
    ) -> list[Memory]:
        """按关键词搜索记忆（排除已被取代的）"""
        memories = self._storage.load(user_id)
        results = [
            m for m in memories
            if not m.is_superseded
            and (keyword in m.content or keyword in m.tags)
        ]

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
        self, user_id: str, memory_id: str, content: str | None = None,
        level: int | None = None, category: str | None = None,
    ) -> Memory | None:
        """更新一条记忆"""
        memories = self._storage.load(user_id)
        for m in memories:
            if m.id == memory_id:
                if content is not None:
                    m.content = content
                if level is not None:
                    m.level = level
                if category is not None:
                    m.category = category
                m.last_accessed = datetime.now().isoformat()
                self._storage.save(user_id, memories)
                logger.info(f"Updated memory {memory_id}")
                return m
        return None

    def get_context_prompt(self, user_id: str, limit: int = 10) -> str:
        """生成记忆上下文 prompt，注入到对话中

        包含分类标签，让 AI 更好地理解记忆类型。
        """
        memories = self.get_memories(user_id, level_min=2, limit=limit)
        if not memories:
            return ""

        # 分类中文名
        category_names = {
            "personal": "个人信息",
            "emotion": "情感",
            "event": "事件",
            "preference": "偏好",
            "relationship": "关系",
            "opinion": "观点",
        }

        lines = ["【你对这个用户的记忆】"]
        for m in memories:
            stars = "⭐" * m.level
            cat = category_names.get(m.category, "")
            cat_tag = f"[{cat}]" if cat else ""
            lines.append(f"- {stars} {cat_tag} {m.content}")

        return "\n".join(lines)

    def get_memories_by_category(
        self, user_id: str, category: str
    ) -> list[Memory]:
        """按分类获取记忆"""
        return self.get_memories(
            user_id, category=category, include_superseded=False
        )

    def import_memories(self, user_id: str, memories_data: list[dict]) -> int:
        """批量导入记忆"""
        existing = self._storage.load(user_id)
        new_memories = [Memory.from_dict(d) for d in memories_data]
        existing.extend(new_memories)
        self._storage.save(user_id, existing)
        logger.info(f"Imported {len(new_memories)} memories for user {user_id}")
        return len(new_memories)

    def export_memories(self, user_id: str) -> list[Memory]:
        """导出用户所有记忆（不含已被取代的）"""
        memories = self._storage.load(user_id)
        return [m for m in memories if not m.is_superseded]

    def _cleanup_old_memories(self, memories: list[Memory]) -> list[Memory]:
        """清理旧记忆：优先保留高重要度的，已被取代的优先清理"""
        # 已被取代的先清理
        superseded = [m for m in memories if m.is_superseded]
        active = [m for m in memories if not m.is_superseded]

        # 如果清理已取代的就够了
        target = self._max_memories
        if len(active) <= target:
            return active + superseded

        # 否则按重要度排序，保留前 N 条
        active.sort(key=lambda m: (m.level, m.last_accessed), reverse=True)
        kept = active[:target]
        removed = len(memories) - len(kept)
        logger.info(f"Cleaned up {removed} old memories")
        return kept