"""StateCollector — 大脑模块状态收集器

从 14 个子系统收集当前状态，聚合为 BrainInput 实例。
所有子系统均为可选，缺失时对应字段设为 None。

用法:
    collector = StateCollector(
        mood_engine=mood_engine,
        open_loop_engine=open_loop_engine,
        ...
    )
    brain_input = await collector.collect(user_id, persona_id)
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from loguru import logger

from .models import BrainInput

if TYPE_CHECKING:
    from core.emotion.mood import MoodEngine
    from core.dialogue.thinker import DialogueThinker
    from core.memory.open_loop import OpenLoopEngine as MemoryOpenLoopEngine
    from core.open_loop import OpenLoopEngine as FlattenedOpenLoopEngine
    from core.dialogue.topic_tracker import TopicTracker
    from core.memory.chat_history import ChatHistoryStorage
    from core.personality.engine import PersonalityEngine
    from core.social.affection.storage import UnifiedAffectionStorage
    from core.memory.identity import IdentityLayer
    from core.memory.life_summary import LifeSummaryEngine as MemoryLifeSummaryEngine
    from core.summary import LifeSummaryEngine as FlattenedLifeSummaryEngine
    from core.persona.loader import PersonaLoader
    from core.persona.drift_monitor import PersonaDriftMonitor
    from core.proactive import ProactiveMessenger
    from core.identity import IdentityStorage
    from core.open_loop import OpenLoopEngine as CoreOpenLoopEngine
    from core.summary import LifeSummaryEngine as CoreLifeSummaryEngine


class StateCollector:
    """大脑模块状态收集器

    收集来自 14 个子系统的状态，返回 BrainInput 实例。
    所有子系统均为可选的 Optional 依赖，缺失时对应字段自动设为 None。
    """

    def __init__(
        self,
        mood_engine: Any = None,
        dialogue_thinker: Any = None,
        open_loop_engine: Any = None,
        topic_tracker: Any = None,
        chat_history: Any = None,
        personality_engine: Any = None,
        affection_storage: Any = None,
        identity: Any = None,
        life_summary: Any = None,
        persona_loader: Any = None,
        drift_monitor: Any = None,
        proactive_messenger: Any = None,
    ):
        """所有参数都是可选的，传 None 的子系统会被静默跳过。"""
        self._mood_engine = mood_engine
        self._dialogue_thinker = dialogue_thinker
        self._open_loop_engine = open_loop_engine
        self._topic_tracker = topic_tracker
        self._chat_history = chat_history
        self._personality_engine = personality_engine
        self._affection_storage = affection_storage
        self._identity = identity
        self._life_summary = life_summary
        self._persona_loader = persona_loader
        self._drift_monitor = drift_monitor
        self._proactive_messenger = proactive_messenger

    async def collect(
        self,
        user_id: str,
        persona_id: str = "girlfriend_001",
    ) -> BrainInput:
        """从所有可用子系统收集状态

        Args:
            user_id: 用户 ID
            persona_id: 人设 ID（默认 girlfriend_001）

        Returns:
            聚合了所有可用子系统状态的 BrainInput 实例
        """
        return BrainInput(
            # 1. 情绪系统
            mood_valence=self._get_mood_valence(user_id),
            mood_arousal=self._get_mood_arousal(user_id),
            mood_energy=self._get_mood_energy(user_id),
            mood_type=self._get_mood_type(user_id),
            mood_intensity=self._get_mood_intensity(user_id),
            # 2. 对话/开放式循环
            dialogue_thought=self._get_dialogue_thought(),
            openloop_events=self._get_openloop_events(user_id),
            current_topic=self._get_current_topic(),
            topic_keywords=self._get_topic_keywords(),
            chat_history_summary=self._get_chat_history_summary(user_id),
            # 3. 人格系统
            personality_trust=self._get_personality_dim(user_id, "trust"),
            personality_dependence=self._get_personality_dim(user_id, "dependence"),
            personality_openness=self._get_personality_dim(user_id, "openness"),
            personality_affection=self._get_personality_dim(user_id, "affection"),
            personality_jealousy=self._get_personality_dim(user_id, "jealousy"),
            # 4. 亲密度系统
            affection_level=self._get_affection_level(user_id, persona_id),
            affection_days_known=self._get_affection_days_known(user_id, persona_id),
            # 5. 身份/人生总结
            identity_context=self._get_identity_context(user_id),
            life_summary=self._get_life_summary(user_id),
            # 6. 人设
            persona_name=self._get_persona_name(persona_id),
            persona_traits=self._get_persona_traits(persona_id),
            drift_report=self._get_drift_report(),
            # 7. 主动行为统计
            proactive_times_today=self._get_proactive_times_today(),
            proactive_last_contact=self._get_proactive_last_contact(),
            # 8. 时间环境
            time_period=self._get_time_period(),
            time_datetime=self._get_time_datetime(),
            # 9. 用户情绪
            user_emotion=self._get_user_emotion(user_id),
            user_emotion_intensity=self._get_user_emotion_intensity(user_id),
        )

    # ────────── Mood ──────────

    def _get_mood(self, user_id: str):
        """获取 MoodState（内部共享）"""
        if not self._mood_engine:
            return None
        try:
            return self._mood_engine.get_mood(user_id)
        except Exception:
            logger.debug("StateCollector: mood_engine.get_mood failed")
            return None

    def _get_mood_valence(self, user_id: str) -> float | None:
        mood = self._get_mood(user_id)
        return getattr(mood, "valence", None) if mood else None

    def _get_mood_arousal(self, user_id: str) -> float | None:
        mood = self._get_mood(user_id)
        return getattr(mood, "arousal", None) if mood else None

    def _get_mood_energy(self, user_id: str) -> float | None:
        mood = self._get_mood(user_id)
        return getattr(mood, "energy", None) if mood else None

    def _get_mood_type(self, user_id: str) -> str | None:
        mood = self._get_mood(user_id)
        if mood is None:
            return None
        try:
            return mood.mood.value if hasattr(mood.mood, "value") else str(mood.mood)
        except Exception:
            return None

    def _get_mood_intensity(self, user_id: str) -> float | None:
        mood = self._get_mood(user_id)
        return getattr(mood, "intensity", None) if mood else None

    # ────────── Dialogue Thought ──────────

    def _get_dialogue_thought(self) -> dict | None:
        """获取对话思考结果

        DialogueThinker 本身不持久化 last_thought，
        但外部调用方（如 ChatPipeline）可能在 thinker 上设置 _last_thought。
        """
        if not self._dialogue_thinker:
            return None
        try:
            return getattr(self._dialogue_thinker, "_last_thought", None)
        except Exception:
            logger.debug("StateCollector: dialogue_thinker._last_thought failed")
            return None

    # ────────── OpenLoop ──────────

    def _get_openloop_events(self, user_id: str) -> list[str] | None:
        """获取活跃事件列表

        支持两种 OpenLoopEngine 实现:
        - core/memory/open_loop.py: 有 get_context() 返回 str
        - core/open_loop.py: 有 get_pending() 返回 list[OpenLoop]
        """
        if not self._open_loop_engine:
            return None
        try:
            # 方法 1: get_context() 返回多行字符串
            context = self._open_loop_engine.get_context(user_id)
            if context:
                lines = [l.strip("- ").strip() for l in context.split("\n") if l.strip()]
                # 过滤掉标题行
                events = [l for l in lines if l and not l.startswith("【")]
                return events if events else None
        except (AttributeError, TypeError):
            pass
        except Exception:
            logger.debug("StateCollector: open_loop_engine.get_context failed")
            pass

        try:
            # 方法 2: get_pending() 返回 OpenLoop 对象列表
            pending = self._open_loop_engine.get_pending(user_id)
            if pending:
                return [getattr(p, "title", str(p)) for p in pending]
        except (AttributeError, TypeError):
            pass
        except Exception:
            logger.debug("StateCollector: open_loop_engine.get_pending failed")

        return None

    # ────────── Topic ──────────

    def _get_current_topic(self) -> str | None:
        if not self._topic_tracker:
            return None
        try:
            topic = self._topic_tracker.get_current_topic()
            return topic if topic else None
        except Exception:
            logger.debug("StateCollector: topic_tracker.get_current_topic failed")
            return None

    def _get_topic_keywords(self) -> list[str] | None:
        if not self._topic_tracker:
            return None
        try:
            topics = self._topic_tracker.get_all_topics()
            return topics if topics else None
        except Exception:
            logger.debug("StateCollector: topic_tracker.get_all_topics failed")
            return None

    # ────────── Chat History ──────────

    def _get_chat_history_summary(self, user_id: str) -> str | None:
        if not self._chat_history:
            return None
        try:
            messages = self._chat_history.get_messages(user_id)
            if not messages:
                return None
            recent = messages[-6:]
            lines = []
            for msg in recent:
                role = msg.get("role", "?")
                content = msg.get("content", "")
                # 截断长消息
                if len(content) > 100:
                    content = content[:100] + "..."
                lines.append(f"[{role}] {content}")
            return "\n".join(lines) if lines else None
        except Exception:
            logger.debug("StateCollector: chat_history.get_messages failed")
            return None

    # ────────── Personality ──────────

    def _get_personality_state(self, user_id: str):
        """获取 PersonalityState（内部共享）"""
        if not self._personality_engine:
            return None
        try:
            return self._personality_engine.get_state(user_id)
        except Exception:
            logger.debug("StateCollector: personality_engine.get_state failed")
            return None

    def _get_personality_dim(self, user_id: str, dim: str) -> float | None:
        state = self._get_personality_state(user_id)
        return getattr(state, dim, None) if state else None

    # ────────── Affection ──────────

    def _get_affection_level(self, user_id: str, persona_id: str) -> float | None:
        if not self._affection_storage:
            return None
        try:
            return self._affection_storage.get_level(user_id, persona_id=persona_id)
        except Exception:
            logger.debug("StateCollector: affection_storage.get_level failed")
            return None

    def _get_affection_days_known(
        self, user_id: str, persona_id: str
    ) -> int | None:
        if not self._affection_storage:
            return None
        try:
            stats = self._affection_storage.get_stats(user_id, persona_id=persona_id)
            return getattr(stats, "days_known", None)
        except Exception:
            logger.debug("StateCollector: affection_storage.get_stats failed")
            return None

    # ────────── Identity ──────────

    def _get_identity_context(self, user_id: str) -> str | None:
        if not self._identity:
            return None
        try:
            context = self._identity.get_context(user_id)
            return context if context else None
        except (AttributeError, TypeError):
            pass
        except Exception:
            logger.debug("StateCollector: identity.get_context failed")
            pass
        # 兼容 core/identity.py 的 IdentityStorage
        try:
            profile = self._identity.load(user_id)
            if profile and hasattr(profile, "to_prompt_section"):
                text = profile.to_prompt_section()
                return text if text else None
        except (AttributeError, TypeError):
            pass
        except Exception:
            logger.debug("StateCollector: identity.load failed")
        return None

    # ────────── Life Summary ──────────

    def _get_life_summary(self, user_id: str) -> str | None:
        if not self._life_summary:
            return None
        # 方法 1: get_context() 返回字符串（core/memory/life_summary.py）
        try:
            context = self._life_summary.get_context(user_id)
            if context:
                return context
        except (AttributeError, TypeError):
            pass
        except Exception:
            logger.debug("StateCollector: life_summary.get_context failed")
            pass
        # 方法 2: get_latest() 返回 LifeSummary（core/summary.py）
        try:
            latest = self._life_summary.get_latest(user_id)
            if latest and hasattr(latest, "to_prompt_section"):
                text = latest.to_prompt_section()
                return text if text else None
        except (AttributeError, TypeError):
            pass
        except Exception:
            logger.debug("StateCollector: life_summary.get_latest failed")
            pass
        # 方法 3: 兼容 load() + to_prompt()
        try:
            summary = self._life_summary.load(user_id)
            if summary and hasattr(summary, "to_prompt"):
                text = summary.to_prompt()
                return text if text else None
        except (AttributeError, TypeError):
            pass
        except Exception:
            logger.debug("StateCollector: life_summary.load failed")
        return None

    # ────────── Persona ──────────

    def _get_persona(self, persona_id: str):
        """获取 Persona（内部共享）"""
        if not self._persona_loader:
            return None
        try:
            return self._persona_loader.get(persona_id)
        except Exception:
            logger.debug("StateCollector: persona_loader.get failed")
            return None

    def _get_persona_name(self, persona_id: str) -> str | None:
        persona = self._get_persona(persona_id)
        return getattr(persona, "name", None) if persona else None

    def _get_persona_traits(self, persona_id: str) -> list[str] | None:
        persona = self._get_persona(persona_id)
        if persona is None:
            return None
        try:
            traits = getattr(persona, "personality", None)
            return traits if traits else None
        except Exception:
            return None

    # ────────── Drift Monitor ──────────

    def _get_drift_report(self) -> str | None:
        """获取人格漂移报告摘要

        PersonaDriftMonitor 是纯分析引擎，不持久化状态。
        这里仅尝试获取其最新分析报告或内部计数器信息。
        """
        if not self._drift_monitor:
            return None
        try:
            # 尝试获取 last_report 或 generate_report_summary
            report = getattr(self._drift_monitor, "_last_report", None)
            if report and hasattr(self._drift_monitor, "generate_report_summary"):
                return self._drift_monitor.generate_report_summary(report)
        except Exception:
            logger.debug("StateCollector: drift_monitor report failed")
        return None

    # ────────── Proactive Messenger ──────────

    def _get_proactive_times_today(self) -> int | None:
        if not self._proactive_messenger:
            return None
        try:
            fired = getattr(self._proactive_messenger, "_fired_today", None)
            if fired is not None:
                return len(fired)
        except Exception:
            logger.debug("StateCollector: proactive._fired_today failed")
        return None

    def _get_proactive_last_contact(self) -> str | None:
        """获取最近一次主动联系的时间"""
        if not self._proactive_messenger:
            return None
        try:
            fired = getattr(self._proactive_messenger, "_fired_today", {})
            if fired:
                # 按值（datetime）排序取最新的
                latest = max(fired.values())
                return latest.isoformat() if hasattr(latest, "isoformat") else str(latest)
        except Exception:
            logger.debug("StateCollector: proactive last_contact failed")
        return None

    # ────────── Time Context ──────────

    @staticmethod
    def _get_time_period() -> str | None:
        """返回当前时段: morning/afternoon/evening/night/late_night"""
        try:
            hour = datetime.now().hour
            if 6 <= hour < 12:
                return "morning"
            elif 12 <= hour < 18:
                return "afternoon"
            elif 18 <= hour < 22:
                return "evening"
            elif 22 <= hour < 24:
                return "night"
            else:  # 0 <= hour < 6
                return "late_night"
        except Exception:
            return None

    @staticmethod
    def _get_time_datetime() -> str | None:
        try:
            return datetime.now().isoformat()
        except Exception:
            return None

    # ────────── User Emotion（from last chat message）──────────

    def _get_user_emotion(self, user_id: str) -> str | None:
        if not self._chat_history:
            return None
        try:
            messages = self._chat_history.get_messages(user_id)
            if not messages:
                return None
            # 找到最近一条 user 消息
            for msg in reversed(messages):
                if msg.get("role") == "user" and msg.get("emotion"):
                    return msg["emotion"]
            return None
        except Exception:
            logger.debug("StateCollector: user emotion failed")
            return None

    def _get_user_emotion_intensity(self, user_id: str) -> float | None:
        if not self._chat_history:
            return None
        try:
            messages = self._chat_history.get_messages(user_id)
            if not messages:
                return None
            # 找到最近一条 user 消息
            for msg in reversed(messages):
                if msg.get("role") == "user" and msg.get("emotion_intensity") is not None:
                    return float(msg["emotion_intensity"])
            return None
        except Exception:
            logger.debug("StateCollector: user emotion intensity failed")
            return None
