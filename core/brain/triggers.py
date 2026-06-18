"""记忆触发模块 — 大脑主动回忆机制

MemoryTrigger 在 Brain 处理用户消息时主动检索记忆，
通过三种触发器（关键词、情绪、自发）从记忆中检索相关内容，
生成内心独白碎片（MonologueThought），保持人设的"主动想起"能力。

用法:
    trigger = MemoryTrigger(memory_mgr)
    thoughts = await trigger.trigger(user_id, user_message, mood_state)
"""

from __future__ import annotations

import random
import re
from datetime import date
from typing import List, Optional

from loguru import logger

from .models import MonologueThought

# 从用户消息中提取有意义的词：2+ 字中文、2+ 字母英文、数字
TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{2,}|[a-zA-Z]{2,}|\d+", re.UNICODE)

# 负面情绪关键词（用于情绪触发）
_NEGATIVE_EMOTION_KEYWORDS: set[str] = {
    "难过",
    "伤心",
    "不开心",
    "累",
    "烦",
    "孤独",
    "焦虑",
    "压力",
    "失望",
    "沮丧",
    "生气",
    "郁闷",
    "痛苦",
    "绝望",
    "疲惫",
    "sad",
    "tired",
    "depressed",
    "lonely",
    "anxious",
    "angry",
    "frustrated",
    "stressed",
    "down",
    "upset",
    "hurt",
}


class MemoryTrigger:
    """记忆触发器

    在 Brain 处理用户消息时主动检索记忆，生成记忆相关的内心独白。
    支持三种触发模式，受频率限制保护：
    - 关键词触发：用户消息中的词命中记忆索引时触发
    - 情绪触发：检测到负面情绪基调时匹配情感记忆
    - 自发触发：随机回忆高重要度记忆（每日上限 3 次）

    频率限制：
    - 每轮最多激活 2 种触发器
    - 每种触发器最多生成 1 条 MonologueThought
    - 自发触发每日上限 3 次
    """

    def __init__(
        self,
        memory_mgr,
        keyword_trigger: bool = True,
        emotion_trigger: bool = True,
        spontaneous_trigger: bool = True,
    ):
        self._memory_mgr = memory_mgr
        self._keyword_enabled = keyword_trigger
        self._emotion_enabled = emotion_trigger
        self._spontaneous_enabled = spontaneous_trigger

        # 自发触发每日计数
        self._spontaneous_count_today: int = 0
        self._spontaneous_date: date = date.today()

    async def trigger(
        self,
        user_id: str,
        user_message: str,
        mood_state=None,
    ) -> List[MonologueThought]:
        """运行所有启用的触发器，收集结果

        Args:
            user_id: 用户 ID
            user_message: 用户当前消息
            mood_state: 可选的情绪状态对象（含 valence 等属性）

        Returns:
            生成的 MonologueThought 列表，受频率限制
        """
        thoughts: List[MonologueThought] = []
        triggered_types = 0  # 本轮已激活的触发器种类数

        # 1. 关键词触发
        if self._keyword_enabled and triggered_types < 2:
            thought = self._keyword_check(user_id, user_message)
            if thought:
                thoughts.append(thought)
                triggered_types += 1

        # 2. 情绪触发
        if self._emotion_enabled and triggered_types < 2:
            thought = self._emotion_check(user_id, user_message, mood_state)
            if thought:
                thoughts.append(thought)
                triggered_types += 1

        # 3. 自发触发
        if self._spontaneous_enabled and triggered_types < 2:
            thought = self._spontaneous_check(user_id)
            if thought:
                thoughts.append(thought)
                triggered_types += 1

        if thoughts:
            logger.debug(
                f"MemoryTrigger: {len(thoughts)} thought(s) generated "
                f"({triggered_types} type(s) activated)"
            )

        return thoughts

    def reset_daily(self) -> None:
        """重置每日计数（在跨天时调用）"""
        self._spontaneous_count_today = 0
        self._spontaneous_date = date.today()
        logger.debug("MemoryTrigger daily counters reset")

    # ────────── 1. 关键词触发 ──────────

    def _keyword_check(
        self,
        user_id: str,
        user_message: str,
    ) -> Optional[MonologueThought]:
        """关键词触发：提取用户消息中的关键词，检索匹配记忆

        对每个提取的词调用 search_memories，命中时生成"想起来"独白。
        """
        try:
            tokens = TOKEN_RE.findall(user_message)
            if not tokens:
                return None

            # 取前 5 个词搜索，避免过度检索
            for token in tokens[:5]:
                if len(token) < 2:
                    continue
                results = self._memory_mgr.search_memories(
                    user_id, token, limit=5,
                )
                if results:
                    memory = results[0]
                    display = (
                        memory.content[:30] + "…"
                        if len(memory.content) > 30
                        else memory.content
                    )
                    return MonologueThought(
                        source="memory_trigger",
                        content=f"对了，他之前说过{display}",
                        priority=0.6,
                        category="memory",
                    )

        except Exception as e:
            logger.debug(f"Keyword trigger failed: {e}")

        return None

    # ────────── 2. 情绪触发 ──────────

    def _emotion_check(
        self,
        user_id: str,
        user_message: str,
        mood_state=None,
    ) -> Optional[MonologueThought]:
        """情绪触发：检测当前情绪基调，匹配情感记忆

        从 mood_state（valence < 0.4）或用户消息关键词判断负面情绪，
        检索分类为 emotion 的记忆生成独白。
        """
        try:
            is_negative = False

            # 从 mood_state 判断（如果有 valence 属性）
            if mood_state is not None:
                try:
                    valence = getattr(mood_state, "valence", None)
                    if valence is not None and valence < 0.4:
                        is_negative = True
                except Exception:
                    pass

            # 从用户消息关键词判断
            if not is_negative:
                msg_lower = user_message.lower()
                if any(kw in msg_lower for kw in _NEGATIVE_EMOTION_KEYWORDS):
                    is_negative = True

            if not is_negative:
                return None

            # 搜索情感类记忆
            memories = self._memory_mgr.get_memories(
                user_id, level_min=2, limit=15, category="emotion",
            )
            if not memories:
                return None

            # 从高相关记忆中随机选一条
            memory = random.choice(memories[:5])
            display = (
                memory.content[:30] + "…"
                if len(memory.content) > 30
                else memory.content
            )
            return MonologueThought(
                source="memory_trigger",
                content=f"他上次这么低落的时候，好像是因为{display}",
                priority=0.65,
                category="memory",
            )

        except Exception as e:
            logger.debug(f"Emotion trigger failed: {e}")

        return None

    # ────────── 3. 自发触发 ──────────

    def _spontaneous_check(
        self,
        user_id: str,
    ) -> Optional[MonologueThought]:
        """自发触发：随机回忆高重要度记忆（level >= 4）

        每日上限 3 次，跨天自动重置。
        从高重要度记忆中随机选择一条生成独白。
        """
        try:
            # 检查每日限制（跨天自动重置）
            today = date.today()
            if today != self._spontaneous_date:
                self.reset_daily()

            if self._spontaneous_count_today >= 3:
                return None

            # 获取高重要度记忆
            memories = self._memory_mgr.get_memories(
                user_id, level_min=4, limit=20,
            )
            if not memories:
                return None

            # 随机选一条
            memory = random.choice(memories)
            display = (
                memory.content[:25] + "…"
                if len(memory.content) > 25
                else memory.content
            )

            self._spontaneous_count_today += 1
            return MonologueThought(
                source="memory_trigger",
                content=f"说起来，他之前说{display}，不知道现在怎么样了",
                priority=0.4,
                category="memory",
            )

        except Exception as e:
            logger.debug(f"Spontaneous trigger failed: {e}")

        return None
