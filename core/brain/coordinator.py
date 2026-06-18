"""BrainCoordinator — 大脑模块统一入口

作为脑模块的唯一对外接口，持有 StateCollector、ThoughtOrganizer、
MonologueWeaver、MemoryTrigger、CharacterBreakDetector 等子组件，
提供 run() 方法一次完成「收集→组织→编织」的完整流程。

用法:
    coordinator = BrainCoordinator(config, mood_engine=mood_engine, ...)
    output = await coordinator.run(user_id, persona_id)
    print(output.monologue)
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from .checker import CharacterBreakDetector
from .collector import StateCollector
from .models import BrainConfig, BrainDisabledError, BrainOutput, MonologueThought
from .organizer import ThoughtOrganizer
from .triggers import MemoryTrigger
from .weaver import MonologueWeaver


class BrainCoordinator:
    """大脑模块协调器 — 所有脑模块子组件的统一入口

    持有所有脑模块子组件：
      - StateCollector（状态收集器）
      - ThoughtOrganizer（念头组织器）
      - MonologueWeaver（内心独白编织器）
      - MemoryTrigger（记忆触发器，可选）
      - CharacterBreakDetector（人设一致性检查器）

    通过 run() 执行完整的「收集→触发→组织→编织→检查」流程。

    Attributes:
        config: BrainConfig 配置实例
        collector: StateCollector 实例
        organizer: ThoughtOrganizer 实例
        weaver: MonologueWeaver 实例
        memory_trigger: MemoryTrigger 实例或 None
        checker: CharacterBreakDetector 实例
    """

    def __init__(
        self,
        config: BrainConfig,
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
        memory_mgr: Any = None,
        persona_name: str = "小雨",
    ):
        """所有子组件参数均为可选依赖，缺失时静默降级。

        Args:
            config: BrainConfig 配置
            persona_name: 人设角色名（给 CharacterBreakDetector）
            **kwargs: 各子系统的实例引用
        """
        if not config.enabled:
            raise BrainDisabledError("Brain is disabled via config")

        self.config = config
        self._persona_name = persona_name

        # 1. StateCollector — 状态收集器
        self.collector = StateCollector(
            mood_engine=mood_engine,
            dialogue_thinker=dialogue_thinker,
            open_loop_engine=open_loop_engine,
            topic_tracker=topic_tracker,
            chat_history=chat_history,
            personality_engine=personality_engine,
            affection_storage=affection_storage,
            identity=identity,
            life_summary=life_summary,
            persona_loader=persona_loader,
            drift_monitor=drift_monitor,
            proactive_messenger=proactive_messenger,
        )

        # 2. ThoughtOrganizer — 念头组织器
        self.organizer = ThoughtOrganizer(max_tokens=config.max_tokens)

        # 3. MonologueWeaver — 内心独白编织器
        self.weaver = MonologueWeaver(max_tokens=config.max_tokens)

        # 4. MemoryTrigger — 记忆触发器（可选）
        self.memory_trigger = MemoryTrigger(memory_mgr) if memory_mgr else None

        # 5. CharacterBreakDetector — 人设一致性检查器
        self.checker = CharacterBreakDetector(
            persona_name=persona_name,
            enabled=config.checker_enabled,
        )

        logger.debug(
            f"BrainCoordinator initialized: max_tokens={config.max_tokens}, "
            f"debug={config.debug}, checker={config.checker_enabled}, "
            f"memory_trigger={self.memory_trigger is not None}"
        )

    async def run(
        self,
        user_id: str,
        persona_id: str = "girlfriend_001",
        user_message: str = "",
    ) -> BrainOutput:
        """完整运行大脑模块

        流程:
            1. StateCollector 收集所有子系统状态 → BrainInput
            2. ThoughtOrganizer 将状态组织为念头 → MonologueThought[]
            3. MemoryTrigger 主动检索记忆（如果有 user_message）→ MonologueThought[]
            4. MonologueWeaver 编织为内心独白 → str
            5. CharacterBreakDetector 检查人设一致性（此处仅初始化，调用方自行 check）

        Args:
            user_id: 用户 ID
            persona_id: 人设 ID（默认 girlfriend_001）
            user_message: 用户当前消息（给 MemoryTrigger 使用，可选）

        Returns:
            BrainOutput: 包含内心独白、原始想法和元数据的统一输出。
        """
        # 1. 收集状态
        brain_input = await self.collector.collect(user_id, persona_id)

        # 2. 组织念头
        thoughts = self.organizer.organize(brain_input)

        # 3. 记忆触发（如果可用且有用户消息）
        trigger_thoughts: list[MonologueThought] = []
        if self.memory_trigger and user_message:
            try:
                # 获取当前 mood 状态给 trigger 使用
                mood_state = None
                if hasattr(self.collector, "_mood_engine") and self.collector._mood_engine:
                    mood_state = self.collector._mood_engine.get_mood(user_id)
                trigger_thoughts = await self.memory_trigger.trigger(
                    user_id, user_message, mood_state,
                )
            except Exception as e:
                logger.debug(f"MemoryTrigger failed: {e}")

        # 合并状态念头 + 触发念头
        all_thoughts = thoughts + trigger_thoughts

        # 4. 编织独白
        if self.config.debug:
            monologue = self.weaver.weave_debug(all_thoughts)
        else:
            monologue = self.weaver.weave(all_thoughts)

        # 5. CharacterBreakDetector 检查需要 LLM 回复文本，
        #    这里只生成内心独白，不生成回复，所以跳过。
        #    调用方（如 ChatPipeline）在获取 LLM 回复后自行调用 checker.check()。

        return BrainOutput(
            monologue=monologue,
            thoughts=all_thoughts,
            metadata={
                "brain_enabled": self.config.enabled,
                "max_tokens": self.config.max_tokens,
                "debug": self.config.debug,
                "thought_count": len(all_thoughts),
                "trigger_count": len(trigger_thoughts),
                "source_count": len(set(t.source for t in all_thoughts)),
                "collector_sources": [
                    t.source for t in thoughts
                ] if self.config.debug else [],
            },
        )

    async def check_character_break(
        self,
        reply: str,
        user_message: str = "",
    ) -> bool:
        """检查回复中的人设崩塌

        Args:
            reply: AI 生成的回复文本
            user_message: 用户上一条消息

        Returns:
            True 如果检测到人设崩塌，False 表示正常
        """
        result = self.checker.check(reply, user_message)
        if result.is_break:
            logger.warning(
                f"Character break detected: {result.trigger_phrase} "
                f"(confidence={result.confidence})"
            )
        return result.is_break

    def get_debug_info(self) -> dict:
        """返回调试用的大脑模块状态信息"""
        return {
            "config": {
                "enabled": self.config.enabled,
                "max_tokens": self.config.max_tokens,
                "debug": self.config.debug,
                "checker_enabled": self.config.checker_enabled,
            },
            "components": {
                "collector": self.collector is not None,
                "organizer": self.organizer is not None,
                "weaver": self.weaver is not None,
                "memory_trigger": self.memory_trigger is not None,
                "checker": self.checker is not None,
                "checker_persona": self._persona_name,
            },
        }
