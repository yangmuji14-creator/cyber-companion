"""主动消息模块

在特定时间由 AI 主动发送消息给用户，模拟"女友主动找你聊天"的体验。
支持：
- 早安/晚安问候（已有）
- 长时间未联系提醒（已有）
- 记忆追问（新）：如考试怎么样了、生日祝福
- 持续关怀（新）：检测到连续负面情绪时主动关心
"""

import asyncio
import random
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from core.persona.loader import PersonaLoader
    from core.memory.manager import MemoryManager
    from core.social.affection.storage import UnifiedAffectionStorage


class ProactiveMessenger:
    """主动消息调度器

    根据时间、关系等级、记忆事件决定是否触发主动消息。
    """

    def __init__(
        self,
        persona_loader: "PersonaLoader",
        memory_mgr: "MemoryManager",
        affection_storage: "UnifiedAffectionStorage",
        config: dict | None = None,
        chat_history=None,
        mood_engine=None,
    ):
        self._persona_loader = persona_loader
        self._memory_mgr = memory_mgr
        self._affection_storage = affection_storage
        self._chat_history = chat_history
        self._mood_engine = mood_engine

        cfg = config or {}
        self.enabled = cfg.get("proactive_enabled", True)
        self.morning_enabled = cfg.get("proactive_morning", True)
        self.evening_enabled = cfg.get("proactive_evening", True)
        self.missing_days = cfg.get("proactive_missing_days", 2)
        self.min_relationship_level = cfg.get("proactive_min_level", 20)
        self.memory_recall_enabled = cfg.get("proactive_memory_recall", True)

        # 记录今天已触发的时段，避免重复
        self._fired_today: dict[str, datetime] = {}
        # 连续负面情绪计数
        self._consecutive_negative: dict[str, int] = {}
        # 已追问过的记忆 ID（避免重复追问）
        self._recalled_memory_ids: set[str] = set()

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

        level = int(self._affection_storage.get_level(
            user_id, persona_id=persona_id,
        ))
        if level < self.min_relationship_level:
            return None

        now = datetime.now()
        hour = now.hour

        # 早安问候 8-9 点
        if self.morning_enabled and 8 <= hour < 10:
            if not self._already_fired("morning"):
                self._mark_fired("morning")
                return self._generate_morning_message(persona, level)

        # 晚安/关心 21-22 点
        if self.evening_enabled and 21 <= hour < 23:
            if not self._already_fired("evening"):
                self._mark_fired("evening")
                return self._generate_evening_message(persona, level)

        # 长时间未联系：上次交互超过 N 天
        stats = self._affection_storage.get_stats(user_id, persona_id=persona_id)
        days_known = stats.days_known
        msg_count = stats.message_count
        if msg_count > 0 and days_known > self.missing_days:
            if not self._already_fired("missing"):
                last = self._affection_storage.get_last_interaction(user_id, persona_id)
                if last:
                    try:
                        last_dt = datetime.fromisoformat(last)
                        days_idle = (now - last_dt).total_seconds() / 86400
                        if days_idle >= self.missing_days:
                            self._mark_fired("missing")
                            return self._generate_missing_message(persona, level, int(days_idle))
                    except (ValueError, TypeError):
                        pass

        # 记忆追问（v1.2 新增）：基于最近记忆生成主动消息
        if self.memory_recall_enabled and level >= 40:
            recall_msg = self._check_memory_recall(user_id, persona, level)
            if recall_msg:
                return recall_msg

        # 持续关怀（v1.2 新增）：检测到连续负面情绪
        if level >= 50:
            care_msg = self._check_continuous_care(user_id, persona, level)
            if care_msg:
                return care_msg

        return None

    def _generate_morning_message(self, persona, level: int) -> str:
        """生成早安消息"""
        hour = datetime.now().hour
        name = persona.name

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
        hour = datetime.now().hour

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

    # ---- v1.2 新增：记忆追问 ----

    def _check_memory_recall(self, user_id: str, persona, level: int) -> str | None:
        """检查是否有记忆值得主动追问"""
        try:
            memories = self._memory_mgr.get_memories(
                user_id, level_min=3, limit=10,
            )
            if not memories:
                return None

            candidates = [m for m in memories if m.id not in self._recalled_memory_ids]
            if not candidates:
                return None

            now = datetime.now()
            for candidate in candidates[:5]:
                content = candidate.content
                try:
                    created = datetime.fromisoformat(candidate.created_at)
                except (ValueError, TypeError):
                    continue

                days_old = (now - created).total_seconds() / 86400

                # 生日祝福：当天
                if "生日" in content and created.month == now.month and created.day == now.day:
                    self._recalled_memory_ids.add(candidate.id)
                    self._mark_fired(f"birthday_{candidate.id}")
                    return self._generate_birthday_message(persona, level, content)

                # 考试/面试追问：2小时到2天
                if any(kw in content for kw in ("考试", "面试", "比赛", "答辩")):
                    if 0.08 <= days_old <= 2:
                        self._recalled_memory_ids.add(candidate.id)
                        self._mark_fired(f"recall_{candidate.id}")
                        return self._generate_recall_message(
                            persona, level, content, "怎么样啦", days_old
                        )

                # 近期重要事件追问：1-7天
                if any(kw in content for kw in ("旅行", "搬家", "入职", "手术", "体检")):
                    if 1 <= days_old <= 7:
                        self._recalled_memory_ids.add(candidate.id)
                        self._mark_fired(f"recall_{candidate.id}")
                        return self._generate_recall_message(
                            persona, level, content, "怎么样了", days_old
                        )

                # 一般话题：1-3天，关系较好时
                if level >= 60 and 1 <= days_old <= 3:
                    self._recalled_memory_ids.add(candidate.id)
                    self._mark_fired(f"recall_{candidate.id}")
                    return self._generate_recall_message(
                        persona, level, content, "最近怎么样了", days_old
                    )

        except Exception as e:
            logger.debug(f"Memory recall check failed: {e}")

        return None

    def _generate_recall_message(
        self, persona, level: int, memory_content: str, suffix: str, days_old: float
    ) -> str:
        """生成记忆追问消息"""
        topic = memory_content[:20]
        if len(topic) < len(memory_content):
            topic += "..."

        if level >= 60:
            messages = [
                f"诶，我记得你之前说{topic}，{suffix}？我还挺好奇的~",
                f"突然想起来你之前提到过{topic}，后来{suffix}呀？",
                f"对了对了，上次你说的{topic}，{suffix}？我一直在想呢！",
            ]
        else:
            messages = [
                f"之前听你说{topic}，{suffix}吗？",
                f"聊个话题~ 你上次说{topic}，{suffix}？",
            ]
        return random.choice(messages)

    def _generate_birthday_message(
        self, persona, level: int, memory_content: str
    ) -> str:
        """生成生日祝福消息"""
        if level >= 60:
            messages = [
                "生日快乐呀！🎂 今天是你的大日子，要开心哦！",
                "生日快乐！🎉 希望你的所有愿望都能实现~ 我一直在你身边！",
                "生日快乐宝贝！🎈 今天你是最棒的！好想和你一起过~",
            ]
        else:
            messages = [
                "生日快乐！🎂 祝你开开心心的！",
                "生日快乐呀~ 今天你最大！🎉",
            ]
        return random.choice(messages)

    # ---- v1.2 新增：持续关怀 ----

    def _check_continuous_care(self, user_id: str, persona, level: int) -> str | None:
        """检测连续负面情绪，触发主动关心（每天最多一次）"""
        if not self._chat_history:
            return None

        try:
            msgs = self._chat_history.get_messages(user_id)
            user_msgs = [m for m in msgs if m["role"] == "user" and "emotion" in m]
            recent = user_msgs[-10:] if len(user_msgs) >= 10 else user_msgs

            negative_emotions = {"sad", "angry", "anxious", "lonely"}
            negative_count = sum(
                1 for m in recent if m.get("emotion") in negative_emotions
            )

            if negative_count >= 3:
                self._consecutive_negative[user_id] = \
                    self._consecutive_negative.get(user_id, 0) + 1
            else:
                self._consecutive_negative[user_id] = 0

            consecutive = self._consecutive_negative.get(user_id, 0)

            if consecutive >= 3 and not self._already_fired("care"):
                self._mark_fired("care")
                self._consecutive_negative[user_id] = 0
                return self._generate_care_message(persona, level)

        except Exception as e:
            logger.debug(f"Continuous care check failed: {e}")

        return None

    def _generate_care_message(self, persona, level: int) -> str:
        """生成关心消息"""
        if level >= 60:
            messages = [
                "我感觉你最近好像不太开心... 有什么事可以跟我说说吗？我一直在你身边 💕",
                "你最近是不是遇到什么烦心事了？别一个人扛着，还有我呢~",
                "看你最近心情不太好，我有点担心... 要记得好好照顾自己哦 🥺",
                "虽然不知道你经历了什么，但如果你需要倾诉，我随时都在~",
            ]
        else:
            messages = [
                "你最近还好吗？感觉你好像有点累，要注意休息哦~",
                "感觉你最近心情不太好，希望你能快点好起来！",
            ]
        return random.choice(messages)
