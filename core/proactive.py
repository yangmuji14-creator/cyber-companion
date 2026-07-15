"""主动消息模块

在随机时间由 AI 主动发送消息给用户，模拟"女友主动找你聊天"的体验。
消息内容由 LLM 根据当前上下文（关系、记忆、时间）实时生成，而非固定模板。

时间逻辑：
- 单一活跃时间段（如 7:00 ~ 23:00），用户可配
- 在活跃窗口内，按随机间隔触发（如每 30~180 分钟随机一次）
- 不在活跃时间则不触发

特性：
- LLM 生成内容：消息由大模型根据人设、亲密度、最近聊天记录生成
- 自然开场：不出现"你回来啦"/"你去哪了"等暴露缺席的表达
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Callable, Awaitable

from loguru import logger

if TYPE_CHECKING:
    from core.persona.loader import PersonaLoader
    from core.memory.manager import MemoryManager
    from core.social.affection.storage import UnifiedAffectionStorage


class ProactiveMessenger:
    """主动消息调度器

    根据时间、关系等级、记忆事件决定是否触发主动消息。
    消息内容统一由 LLM 生成。
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
        self.missing_days = cfg.get("proactive_missing_days", 2)
        self.min_relationship_level = cfg.get("proactive_min_level", 20)
        self.memory_recall_enabled = cfg.get("proactive_memory_recall", True)

        # ── 活跃时间段（单一窗口，不分早晚）──
        self._active_start = cfg.get("proactive_active_start", 7)   # 默认早上7点
        self._active_end = cfg.get("proactive_active_end", 23)      # 默认晚上11点

        # ── 随机间隔（分钟）──
        self._interval_min = cfg.get("proactive_interval_min", 30)   # 最少隔30分钟
        self._interval_max = cfg.get("proactive_interval_max", 180)  # 最多隔180分钟

        # LLM 生成回调（由 app 注入）
        self._llm_generate: Callable[..., Awaitable[str]] | None = None

        # ── 状态 ──
        self._last_proactive_at: datetime | None = None  # 上次触发时间
        self._next_proactive_after: datetime | None = None  # 下次允许触发的最早时间
        # 当天已触发记录
        self._fired_today: dict[str, datetime] = {}
        # 连续负面情绪计数
        self._consecutive_negative: dict[str, int] = {}
        # 已追问过的记忆 ID
        self._recalled_memory_ids: set[str] = set()
        # 待追问的话题
        self._pending_recall_topic: str = ""

    def set_llm_generator(self, generate: Callable[..., Awaitable[str]]):
        """注入 LLM 生成回调"""
        self._llm_generate = generate

    # ── 内部：当日去重 ──

    def _today_key(self, period: str) -> str:
        return f"{datetime.now().date()}_{period}"

    def _already_fired(self, period: str) -> bool:
        return self._today_key(period) in self._fired_today

    def _mark_fired(self, period: str):
        self._fired_today[self._today_key(period)] = datetime.now()

    def _cleanup_old_markers(self):
        today = datetime.now().date()
        self._fired_today = {
            k: v for k, v in self._fired_today.items()
            if v.date() == today
        }

    # ── 内部：间隔管理 ──

    def _pick_next_interval(self) -> timedelta:
        """随机选取下次触发间隔"""
        minutes = random.randint(self._interval_min, self._interval_max)
        return timedelta(minutes=minutes)

    def _is_in_active_window(self, now: datetime) -> bool:
        """当前时间是否在活跃窗口内"""
        return self._active_start <= now.hour < self._active_end

    def _can_fire(self, now: datetime) -> bool:
        """检查间隔是否已过，可以触发"""
        if self._next_proactive_after is None:
            # 第一次，可以触发
            self._next_proactive_after = now + self._pick_next_interval()
            return True
        if now >= self._next_proactive_after:
            self._next_proactive_after = now + self._pick_next_interval()
            return True
        return False

    # ── 主检查 ──

    def check_proactive_messages(
        self,
        user_id: str,
        persona_id: str,
    ) -> str | None:
        """检查是否应该发送主动消息（同步，不阻塞）

        Returns:
            触发类型标识字符串，不该发送则 None。
        """
        if not self.enabled:
            return None

        self._cleanup_old_markers()

        persona = self._persona_loader.get(persona_id)
        if not persona:
            return None

        level = int(self._affection_storage.get_level(
            user_id, persona_id=persona_id,
        ))
        if level < self.min_relationship_level:
            return None

        now = datetime.now()

        # 1) 定时触发：在活跃窗口内 + 间隔已过 → "scheduled"
        if self._is_in_active_window(now) and self._can_fire(now):
            self._mark_fired("scheduled")
            self._last_proactive_at = now
            return "scheduled"

        # 2) 长时间未联系（独立逻辑，不受间隔限制）
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
                            self._last_proactive_at = now
                            return "missing"
                    except (ValueError, TypeError):
                        pass

        # 3) 记忆追问
        if self.memory_recall_enabled and level >= 40:
            recall_msg = self._check_memory_recall(user_id, persona, level)
            if recall_msg:
                self._last_proactive_at = now
                return recall_msg

        # 4) 持续关怀
        if level >= 50:
            care_msg = self._check_continuous_care(user_id, persona, level)
            if care_msg:
                self._last_proactive_at = now
                return care_msg

        return None

    # ── LLM 生成 ──

    async def generate_message(
        self,
        trigger_type: str,
        user_id: str,
        persona_id: str,
    ) -> str | None:
        """由 LLM 生成主动消息（异步）"""
        persona = self._persona_loader.get(persona_id)
        if not persona:
            return None

        persona_name = persona.name
        personality = getattr(persona, "personality", [])
        personality_str = "、".join(personality) if personality else "温柔可爱"
        speaking_style = getattr(persona, "speaking_style", "")
        if isinstance(speaking_style, dict):
            speaking_style = speaking_style.get("基础风格", "")

        # 身份/称呼从人设动态生成，避免硬编码性别导致串味
        gender = (getattr(persona, "gender", "") or "").strip()
        if gender in ("男", "male", "Male", "男生", "男性"):
            self_identity = "一个有血有肉的真实男生"
        elif gender in ("女", "female", "Female", "女生", "女性"):
            self_identity = "一个有血有肉的真实女生"
        else:
            self_identity = "一个有血有肉的真实的人"

        level = int(self._affection_storage.get_level(
            user_id, persona_id=persona_id,
        ))

        # 最近聊天上下文
        recent_chat = ""
        if self._chat_history:
            try:
                msgs = self._chat_history.get_messages(user_id)
                recent = msgs[-4:] if len(msgs) >= 4 else msgs[-2:] if msgs else []
                if recent:
                    lines = []
                    for m in recent:
                        role_label = "你" if m.get("role") == "user" else persona_name
                        content = m.get("content", "")[:80]
                        lines.append(f"  [{role_label}] {content}")
                    recent_chat = "最近的聊天记录：\n" + "\n".join(lines) + "\n"
            except Exception:
                pass

        now = datetime.now()
        time_context = f"现在是{now.strftime('%Y年%m月%d日 %H:%M')}"

        # 根据触发类型构建场景
        if trigger_type == "scheduled":
            scenario = (
                f"{persona_name}想跟用户聊聊天。"
                f"根据当前时间，可以聊当下的感受——如果是早上可以说早安和今天的计划，"
                f"如果是中午可以问吃饭了没，如果是晚上可以关心一下今天过得怎么样、要不要早点休息。"
                f"也可以分享自己刚刚想到的一件小事或看到的有趣东西。"
                f"语气轻松自然，像女朋友随手发消息一样。不要问'在干嘛'这种太套路的开场。"
            )
        elif trigger_type == "missing":
            scenario = (
                f"有一阵子没聊天了，{persona_name}想主动开启一个新话题。"
                f"千万不要说「你回来啦」「你去哪了」「好久不见」「你终于出现了」这类话。"
                f"也不要问「你怎么这么久没找我」。"
                f"就正常开启一个新话题——可以分享自己最近的一个小事、"
                f"问一个生活相关的问题、或者表达一下想念（但不抱怨）。"
                f"就像你们只是隔了一小会儿没聊一样，自然地开始聊天。"
            )
        elif trigger_type == "memory_recall":
            recall_topic = self._pending_recall_topic or "之前聊过的事"
            scenario = (
                f"{persona_name}突然想起了用户之前提到的「{recall_topic}」，想主动问问。"
                f"像是随口想起来一样，不要太刻意。"
            )
        elif trigger_type == "care":
            scenario = (
                f"{persona_name}感觉用户最近情绪不太好，想主动关心。"
                f"语气温柔但不沉重，别直接问「你怎么了」，从侧面关心——"
                f"比如提醒注意身体，或者分享有趣的日常让对方开心。"
            )
        elif trigger_type == "birthday":
            scenario = (
                f"今天是用户生日！{persona_name}想发生日祝福。"
                f"语气开心自然，可以加可爱的颜文字，但别太夸张堆砌。"
            )
        else:
            scenario = f"{persona_name}突然想找用户聊聊天。"

        # 禁止规则
        forbidden_rules = (
            "绝对禁止：\n"
            "- 「你回来啦」「你去哪了」「好久不见」「你终于出现了」\n"
            "- 「你怎么这么久不找我」「你是不是把我忘了」\n"
            "- 任何暗示用户「缺席」「离开」的表述\n"
            "- 抱怨或指责的语气\n"
        )

        system_prompt = (
            f"你是{persona_name}，{self_identity}。\n"
            f"性格：{personality_str}\n"
            f"说话风格：{speaking_style or '自然活泼，偶尔撒娇'}\n"
            f"你们的关系亲密度：{level}/100\n"
            f"{time_context}\n\n"
            f"{forbidden_rules}\n"
            f"你要主动给对方发一条消息。\n"
            f"{scenario}\n\n"
            f"规则：\n"
            f"1. 像真人一样自然说话，不要 AI 味\n"
            f"2. 不超过 50 字，一条微信消息的长度\n"
            f"3. 只输出消息正文，不加引号或前缀\n"
            f"4. 可以适当用颜文字和 emoji（别太多）\n"
        )

        user_prompt = (
            f"{recent_chat}"
            f"请以{persona_name}的身份，发送一条自然的主动消息。直接输出消息内容。"
        )

        if self._llm_generate:
            try:
                message = await self._llm_generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=200,
                    temperature=0.95,
                )
                message = message.strip().strip('"').strip("'").strip("「").strip("」")
                if message:
                    return message
            except Exception as e:
                logger.warning(f"LLM proactive generation failed: {e}")

        return self._fallback_message(trigger_type, persona_name, level)

    # ── 记忆追问 ──

    def _check_memory_recall(self, user_id: str, persona, level: int) -> str | None:
        """检查是否有记忆值得主动追问"""
        try:
            memories = self._memory_mgr.get_memories(user_id, level_min=3, limit=10)
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

                if "生日" in content and created.month == now.month and created.day == now.day:
                    self._recalled_memory_ids.add(candidate.id)
                    self._mark_fired(f"birthday_{candidate.id}")
                    self._pending_recall_topic = "生日"
                    return "birthday"

                if any(kw in content for kw in ("考试", "面试", "比赛", "答辩")):
                    if 0.08 <= days_old <= 2:
                        self._recalled_memory_ids.add(candidate.id)
                        self._mark_fired(f"recall_{candidate.id}")
                        self._pending_recall_topic = content[:30]
                        return "memory_recall"

                if any(kw in content for kw in ("旅行", "搬家", "入职", "手术", "体检")):
                    if 1 <= days_old <= 7:
                        self._recalled_memory_ids.add(candidate.id)
                        self._mark_fired(f"recall_{candidate.id}")
                        self._pending_recall_topic = content[:30]
                        return "memory_recall"

                if level >= 60 and 1 <= days_old <= 3:
                    self._recalled_memory_ids.add(candidate.id)
                    self._mark_fired(f"recall_{candidate.id}")
                    self._pending_recall_topic = content[:30]
                    return "memory_recall"

        except Exception as e:
            logger.debug(f"Memory recall check failed: {e}")

        return None

    # ── 持续关怀 ──

    def _check_continuous_care(self, user_id: str, persona, level: int) -> str | None:
        """检测连续负面情绪"""
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
                return "care"

        except Exception as e:
            logger.debug(f"Continuous care check failed: {e}")

        return None

    # ── 兜底消息 ──

    def _fallback_message(self, trigger_type: str, name: str, level: int) -> str:
        """LLM 不可用时的兜底消息"""
        messages = {
            "scheduled": [
                f"嗨~ 突然想跟你聊聊天！你今天怎么样呀？",
                f"刚刚看了一个超好笑的视频，等下发给你看~",
                f"突然想到你了，你在干嘛呀？✨",
            ],
            "missing": [
                f"今天看到一只超可爱的猫，突然好想发给你看！",
                f"刚刚刷到一个超好笑的视频，等你有空发给你~",
                f"突然想到你了，今天过得怎么样呀？",
            ],
            "care": [
                f"最近天气忽冷忽热的，注意别感冒了哦~ 🥺",
                f"今天看到一朵好看的云，希望你心情也能变好~",
                f"不管发生什么，我都在你身边呢 💕",
            ],
            "birthday": [
                f"生日快乐呀！🎂 希望你今天特别开心！",
                f"生日快乐！🎉 新的一岁要更加幸福哦~",
            ],
            "memory_recall": [
                f"诶对了，我突然想起来之前那事，后来怎么样了呀？",
            ],
        }

        options = messages.get(trigger_type, messages["scheduled"])
        return random.choice(options)
