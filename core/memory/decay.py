"""记忆衰减系统 — 模拟遗忘机制

根据时间、重要度、访问频率计算每条记忆的 forget_score。
当 forget_score 超过阈值且重要度不足时，自动归档记忆。

衰减规则：
- 每天基础衰减：forget_score += decay_rate
- 高重要度 (level 4-5) 衰减慢：decay_rate * 0.3
- 中等重要度 (level 3) 衰减中：decay_rate * 0.6
- 低重要度 (level 1-2) 衰减快：decay_rate * 1.0
- 高访问频率衰减慢：forget_score -= access_count * 0.005
- 最近访问过的衰减慢：24h 内访问过则 forget_score -= 0.02

归档条件：
- forget_score >= threshold（默认 1.0）
- 且 level < 3
- 自动标记 archived = True
"""

import math
from datetime import datetime, timedelta
from typing import Callable

from loguru import logger

from .models import Memory


class MemoryDecaySystem:
    """记忆衰减系统

    周期性扫描所有记忆，计算 forget_score，归档过时记忆。
    """

    # 重要度对应的衰减速率倍率
    LEVEL_DECAY_MULTIPLIERS = {
        1: 1.0,   # 不重要 → 快速遗忘
        2: 0.8,
        3: 0.5,   # 中等 → 中等遗忘
        4: 0.3,
        5: 0.15,  # 非常重要 → 几乎不忘
    }

    # 分类衰减修正（某些分类更容易被遗忘）
    CATEGORY_DECAY_MODIFIERS = {
        "event": 0.8,        # 事件衰减稍快
        "opinion": 0.7,      # 观点衰减较快
        "preference": 0.6,   # 偏好衰减中等
        "emotion": 0.5,      # 情感衰减慢
        "personal": 0.3,     # 个人信息衰减很慢
        "relationship": 0.4, # 关系信息衰减慢
        "other": 0.9,        # 其他衰减快
    }

    def __init__(
        self,
        base_decay_rate: float = 0.01,        # 每天基础衰减率
        forget_threshold: float = 1.0,          # 归档阈值
        access_decay_bonus: float = 0.005,      # 每次访问减少的 forget_score
        recent_access_bonus: float = 0.02,      # 最近访问的减少量
        recent_hours: int = 24,                 # "最近访问"的时间窗口
    ):
        self._base_decay_rate = base_decay_rate
        self._forget_threshold = forget_threshold
        self._access_decay_bonus = access_decay_bonus
        self._recent_access_bonus = recent_access_bonus
        self._recent_hours = recent_hours

    def calculate_forget_score(self, memory: Memory) -> float:
        """计算单条记忆的当前 forget_score

        综合：时间衰减 + 重要度修正 + 访问频率修正 + 最近访问修正
        """
        now = datetime.now()

        try:
            created = datetime.fromisoformat(memory.created_at)
            last_acc = datetime.fromisoformat(memory.last_accessed)
        except (ValueError, TypeError):
            created = now
            last_acc = now

        # 1. 基础时间衰减（从创建到现在）
        days_existed = max(0.0, (now - created).total_seconds() / 86400)
        level_mult = self.LEVEL_DECAY_MULTIPLIERS.get(memory.level, 1.0)
        cat_mod = self.CATEGORY_DECAY_MODIFIERS.get(memory.category, 1.0)
        base_score = days_existed * self._base_decay_rate * level_mult * cat_mod

        # 2. 访问频率修正
        access_bonus = memory.access_count * self._access_decay_bonus

        # 3. 最近访问修正（24h 内访问过则减分）
        hours_since_access = (now - last_acc).total_seconds() / 3600
        recent_bonus = self._recent_access_bonus if hours_since_access < self._recent_hours else 0.0

        # 4. 已 superseded 的记忆额外加分（更容易遗忘）
        superseded_penalty = 0.3 if memory.is_superseded else 0.0

        # 综合计算
        forget_score = base_score - access_bonus - recent_bonus + superseded_penalty
        return max(0.0, forget_score)

    def should_archive(self, memory: Memory) -> bool:
        """判断记忆是否应该被归档

        条件：
        1. forget_score >= threshold
        2. level < 3
        3. 未被 superseded（已取代的记忆单独处理）
        """
        if memory.is_superseded:
            # 已取代的记忆直接标记为可清理
            return True
        if memory.archived:
            return False  # 已归档
        if memory.level >= 3:
            return False  # 高重要度不归档
        forget_score = self.calculate_forget_score(memory)
        return forget_score >= self._forget_threshold

    def get_retrieval_weight(self, memory: Memory) -> float:
        """计算检索权重（用于排序）

        综合置信度、重要度、时效性、忘性。
        权重越高，越容易被检索到。
        """
        if memory.archived or memory.is_superseded:
            return 0.0

        now = datetime.now()
        try:
            last_acc = datetime.fromisoformat(memory.last_accessed)
            hours_since = (now - last_acc).total_seconds() / 3600
        except (ValueError, TypeError):
            hours_since = 0

        # 基础分：重要度 + 置信度
        base = (memory.level / 5.0) * 0.4 + memory.confidence * 0.3

        # 时效性加分：最近访问过的加权
        recency = max(0.0, 1.0 - hours_since / 720) * 0.2  # 30 天衰减到 0

        # 访问频率加分
        frequency = min(1.0, memory.access_count / 20) * 0.1

        return base + recency + frequency

    @staticmethod
    def archive_memory(memory: Memory) -> Memory:
        """归档一条记忆"""
        memory.archived = True
        logger.debug(f"Archived memory: {memory.content[:30]}...")
        return memory

    def apply_forget_decay(self, user_id: str, memories: list[Memory]) -> int:
        """应用遗忘衰减（manager.py 集成用）
        
        Args:
            user_id: 用户 ID（仅日志用）
            memories: 用户的记忆列表（会被原地更新）

        Returns:
            受影响的记忆数
        """
        affected = 0
        for mem in memories:
            if mem.archived or mem.is_superseded:
                continue
            old_score = mem.forget_score
            mem.forget_score = self.calculate_forget_score(mem)
            if mem.forget_score > old_score:
                affected += 1
        return affected

    def process_memories(self, memories: list[Memory]) -> list[Memory]:
        """批量处理记忆：更新 forget_score + 归档

        Args:
            memories: 用户的所有记忆

        Returns:
            处理后的记忆列表
        """
        processed = []
        archived_count = 0
        for mem in memories:
            if mem.archived:
                processed.append(mem)
                continue
            mem.forget_score = self.calculate_forget_score(mem)
            if self.should_archive(mem):
                self.archive_memory(mem)
                archived_count += 1
            processed.append(mem)
        if archived_count:
            logger.info(f"Archived {archived_count} memories (threshold={self._forget_threshold})")
        return processed
