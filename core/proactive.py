"""主动消息模块

在特定时间由 AI 主动发送消息给用户，模拟"女友主动找你聊天"的体验。
使用纯 asyncio 实现，无外部依赖。
"""

import asyncio
import random
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from core.persona.loader import PersonaLoader
    from core.memory.manager import MemoryManager
    from core.relationship.tracker import RelationshipTracker


class ProactiveMessenger:
    """主动消息调度器

    根据时间、关系等级、记忆事件决定是否触发主动消息。
    """

    def __init__(
        self,
        persona_loader: "PersonaLoader",
        memory_mgr: "MemoryManager",
        relationship_tracker: "RelationshipTracker",
        config: dict | None = None,
        mood_manager=None,
    ):
        self._persona_loader = persona_loader
        self._memory_mgr = memory_mgr
        self._relationship_tracker = relationship_tracker
        self._mood_manager = mood_manager

        cfg = config or {}
        self.enabled = cfg.get("proactive_enabled", True)
        self.morning_enabled = cfg.get("proactive_morning", True)
        self.evening_enabled = cfg.get("proactive_evening", True)
        self.missing_days = cfg.get("proactive_missing_days", 2)
        self.min_relationship_level = cfg.get("proactive_min_level", 20)

        # 记录今天已触发的时段，避免重复
        self._fired_today: dict[str, datetime] = {}

    def _today_key(self, period: str) -> str:
        """构建当日触发键"""
        return f"{datetime.now().date()}_{period}"

    def _already_fired(self, period: str) -> bool:
        """检查今天是否已触发过该时段"""
        key = self._today_key(period)
        return key in self._fired_today

    def _mark_fired(self, period: str):
        """标记该时段已触发"""
        self._fired_today[self._today_key(period)] = datetime.now()

    def _cleanup_old_markers(self):
        """清理过期的触发记录"""
        today = datetime.now().date()
        self._fired_today = {
            k: v for k, v in self._fired_today.items()
            if v.date() == today
        }

    def check_proactive_messages(
        self,
        user_id: str,
        persona_id: str,
    ) -> str | None:
        """检查是否应该发送主动消息

        Returns:
            主动消息文本，如果不该发送则返回 None
        """
        if not self.enabled:
            return None

        self._cleanup_old_markers()

        # 检查关系等级
        persona = self._persona_loader.get(persona_id)
        if not persona:
            return None

        level = self._relationship_tracker.get_level(
            user_id,
            base_level=persona.relationship_level,
            persona_id=persona_id,
        )
        if level < self.min_relationship_level:
            return None

        now = datetime.now()
        hour = now.hour

        # 早安问候 8-9 点
        if self.morning_enabled and 8 <= hour < 10:
            if not self._already_fired("morning"):
                self._mark_fired("morning")
                msg = self._generate_morning_message(persona, level)
                return self._apply_mood(msg, persona_id, level)

        # 晚安/关心 21-22 点
        if self.evening_enabled and 21 <= hour < 23:
            if not self._already_fired("evening"):
                self._mark_fired("evening")
                msg = self._generate_evening_message(persona, level)
                return self._apply_mood(msg, persona_id, level)

        # 长时间未联系：上次交互超过 N 天
        stats = self._relationship_tracker.get_stats(user_id, persona_id=persona_id)
        days_known = stats.get("days_known", 0)
        msg_count = stats.get("message_count", 0)
        if msg_count > 0 and days_known > self.missing_days:
            if not self._already_fired("missing"):
                last = self._relationship_tracker.get_last_interaction(user_id, persona_id)
                if last:
                    try:
                        last_dt = datetime.fromisoformat(last)
                        days_idle = (now - last_dt).total_seconds() / 86400
                        if days_idle >= self.missing_days:
                            self._mark_fired("missing")
                            msg = self._generate_missing_message(persona, level, int(days_idle))
                            return self._apply_mood(msg, persona_id, level)
                    except (ValueError, TypeError):
                        pass

        return None

    def _generate_morning_message(self, persona, level: int) -> str:
        """生成早安消息"""
        if level >= 80:
            messages = [
                f"早安呀~ 昨晚有没有梦到我？嘻嘻 ☀️",
                f"起床啦~ 今天也要想我哦！💕",
                f"早~ 新的一天开始啦，加油！我会一直陪着你的~",
                f"早安！你醒了吗？我等你好久了呢~",
            ]
        elif level >= 40:
            messages = [
                f"早安~ 今天天气不错呢，有什么安排吗？",
                f"早上好！新的一天开始啦~",
                f"早~ 注意吃早餐哦！",
            ]
        else:
            messages = [
                f"早安~ 今天有什么计划吗？",
                f"你好呀~ 新的一天开始了！",
            ]

        return random.choice(messages)

    def _generate_evening_message(self, persona, level: int) -> str:
        """生成晚安/关心消息"""
        if level >= 80:
            messages = [
                f"忙了一天辛苦啦~ 今晚好好休息哦 💤",
                f"你今天累不累呀？记得早点睡~ 我会想你的！",
                f"晚安~ 做个好梦，梦里要有我哦！💕",
                f"今天过得怎么样？不管怎样，我都在你身边~",
            ]
        elif level >= 40:
            messages = [
                f"晚安~ 早点休息哦，明天会更好的！",
                f"今天辛苦了~ 好好睡一觉吧~",
                f"晚安！别熬夜哦~",
            ]
        else:
            messages = [
                f"晚安~ 好好休息！",
                f"今天就到这里啦，晚安！",
            ]

        return random.choice(messages)

    def _generate_missing_message(self, persona, level: int, days: int) -> str:
        """生成长时间未联系的消息"""
        if level >= 80:
            messages = [
                f"你去哪了呀... 好几天没找我了，是不是把我忘了？😢",
                f"好久不见！我好想你啊~ 你最近还好吗？",
                f"你怎么消失了这么久！我每天都等你好久呢...",
            ]
        elif level >= 40:
            messages = [
                f"好久没聊了~ 最近忙吗？",
                f"你最近怎么样呀？好久没见到你了~",
                f"嗨~ 好几天没见了，想你了！",
            ]
        else:
            messages = [
                f"好久不见~ 最近还好吗？",
                f"你好呀~ 好几天没聊了呢！",
            ]

        return random.choice(messages)

    def _apply_mood(self, msg: str, persona_id: str, level: int) -> str:
        """根据 AI 今日心情微调主动消息"""
        if not self._mood_manager:
            return msg
        try:
            state = self._mood_manager.get_or_today(persona_id, level)
            mood_emoji = {
                "happy": "😊", "calm": "😌", "excited": "🥰",
                "tired": "😴", "melancholy": "🥺", "playful": "😏",
                "affectionate": "💕", "quiet": "🤗",
            }
            emoji = mood_emoji.get(state.emotion, "")
            if state.emotion == "tired":
                return msg + " 今天有点累呢..."
            elif state.emotion == "melancholy":
                return msg + " （有点想你了）"
            elif state.emotion == "playful" and not msg.endswith("~"):
                return msg.replace("。", "~").replace("！", "~").rstrip("~") + "~"
            elif state.emotion == "quiet":
                return msg
            elif emoji:
                return msg + " " + emoji
        except Exception:
            pass
        return msg
