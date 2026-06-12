"""MultiLayerMemoryManager — 多层记忆管理器

统一管理四层记忆：
- Working Memory: 当前对话上下文
- Short Term Memory: 最近7天摘要
- Long Term Memory: 重要事实
- Life Summary: 用户画像和变化追踪

提供统一的检索接口，自动协调各层记忆。
"""

from pathlib import Path
import uuid
from typing import TYPE_CHECKING

from loguru import logger

from .working_memory import WorkingMemory, Message
from .short_term import ShortTermMemory, DailySummary
from .long_term import LongTermMemory, LongTermFact
from .life_summary import LifeSummary, UserProfile, InterestChange, RelationshipChange

if TYPE_CHECKING:
    from ..embedder import BaseEmbedder
    from ..vector_store import VectorStore


class MultiLayerMemoryManager:
    """多层记忆管理器"""

    def __init__(
        self,
        data_dir: str | Path,
        working_memory_size: int = 30,
        short_term_days: int = 7,
        embedder: "BaseEmbedder | None" = None,
        vector_store: "VectorStore | None" = None,
    ):
        self._data_dir = Path(data_dir)

        # 初始化四层记忆
        self.working_memory = WorkingMemory(max_messages=working_memory_size)
        self.short_term = ShortTermMemory(str(data_dir), retention_days=short_term_days)
        self.long_term = LongTermMemory(str(data_dir))
        self.life_summary = LifeSummary(str(data_dir))

        # 可选的向量索引
        self._embedder = embedder
        self._vector_store = vector_store

    def add_working_message(self, role: str, content: str, emotion: str = "", importance: int = 3) -> None:
        """添加工作记忆消息"""
        msg = Message(role=role, content=content, emotion=emotion, importance=importance)
        self.working_memory.add(msg)

    def add_long_term_fact(self, content: str, category: str = "other", importance: int = 3, tags: list[str] | None = None) -> None:
        """添加长期事实"""
        fact = LongTermFact(
            id=f"fact_{uuid.uuid4().hex[:8]}",
            content=content,
            category=category,
            importance=importance,
            tags=tags or [],
        )
        self.long_term.add_fact(fact)

    def add_daily_summary(self, summary: DailySummary) -> None:
        """添加每日摘要"""
        self.short_term.add_summary(summary)

    def update_user_profile(self, profile: UserProfile) -> None:
        """更新用户画像"""
        self.life_summary.update_profile(profile)

    def get_unified_context(self, query: str = "", limit_per_layer: int = 5) -> str:
        """获取统一的记忆上下文（从所有层）

        检索策略：
        1. 工作记忆：最近的消息
        2. 短期记忆：最近几天的摘要
        3. 长期记忆：与 query 相关的重要事实
        4. 生活总结：用户画像和变化

        最终排序：语义相似度 × 0.4 + 重要度 × 0.3 + 时效 × 0.3
        """
        parts = []

        # 1. 工作记忆
        working_summary = self.working_memory.get_summary()
        if working_summary and working_summary != "暂无对话记录":
            parts.append(f"【当前对话】\n{working_summary}")

        # 2. 短期记忆
        short_term_prompt = self.short_term.get_context_prompt(days=3)
        if short_term_prompt:
            parts.append(short_term_prompt)

        # 3. 长期记忆
        long_term_prompt = self.long_term.get_context_prompt(query, limit=limit_per_layer)
        if long_term_prompt:
            parts.append(long_term_prompt)

        # 4. 生活总结
        life_summary_prompt = self.life_summary.get_context_prompt()
        if life_summary_prompt:
            parts.append(life_summary_prompt)

        if not parts:
            return ""

        return "\n\n".join(parts)

    def search_all_layers(self, query: str, limit: int = 10) -> dict[str, list]:
        """在所有层搜索相关内容"""
        results = {
            "working": [],
            "short_term": [],
            "long_term": [],
            "life_summary": [],
        }

        # 工作记忆搜索
        for msg in self.working_memory.get_all():
            if query in msg.content:
                results["working"].append(msg)

        # 长期记忆搜索
        results["long_term"] = self.long_term.search_by_keyword(query, limit)

        return results

    def get_stats(self) -> dict[str, int]:
        """获取各层记忆统计"""
        return {
            "working_memory": self.working_memory.size,
            "short_term": self.short_term.size,
            "long_term": self.long_term.size,
        }

    def clear_working_memory(self) -> None:
        """清空工作记忆（会话结束时调用）"""
        self.working_memory.clear()

    def export_all(self) -> dict:
        """导出所有记忆数据"""
        return {
            "working_memory": self.working_memory.to_dict(),
            "short_term": self.short_term.to_dict(),
            "life_summary": self.life_summary.to_dict(),
            "stats": self.get_stats(),
        }
