"""ChatPipeline — 消息处理管线

从用户消息到 AI 回复的完整流程：
  情绪分析 → Mood更新 → 记忆检索（向量/关键词）→ Prompt构建（含Mood/人格/工具）
  → LLM调用（支持工具调用）→ 工具执行（如有）→ 最终回复
  → 记忆保存（含向量索引）→ 人格更新 → 后台 LLM 提取+总结

用法:
    pipeline = ChatPipeline(llm, memory_mgr, persona_loader, personality_engine,
                            chat_history, llm_emotion_analyzer, relationship_tracker, config)
    reply, level = await pipeline.process(user_id, content, persona_id)
"""

import asyncio
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from loguru import logger

from core.emotion import EmotionEnhancer, MoodExpressionEngine
from core.dialogue import DialogueThinker, PersonaConsistencyChecker, ConsistencyGuard
from core.memory import MemorySummarizer
from core.multimodal import StickerReplier
from core.persona import PromptBuilder
from core.social.relationship import RelationshipEvolution
from core.social.relationship.events import RelationshipEventTracker
from core.persona.drift_monitor import PersonaDriftMonitor
from core.social.affection.storage import UnifiedAffectionStorage
from core.brain import BrainCoordinator
from core.chat.tool_handler import parse_tool_call, build_tools_prompt, call_llm_with_tools
from core.chat.post_process import PostProcessOrchestrator


# ========== 模块级工具函数（可独立测试）==========

def format_multi_message(content: str) -> tuple[str, int]:
    """将多行消息格式化为 [消息1]/[消息2]... 格式"""
    lines = [line.strip() for line in content.split("\n") if line.strip()]
    if len(lines) <= 1:
        return content, 1
    formatted = "\n".join(f"[消息{i}] {line}" for i, line in enumerate(lines, 1))
    return formatted, len(lines)


def get_time_context() -> str:
    """返回当前时段描述，如「现在是下午 2026-06-11 14:30」"""
    now = datetime.now()
    hour = now.hour
    if 0 <= hour < 6:
        period = "深夜"
    elif 6 <= hour < 9:
        period = "早上"
    elif 9 <= hour < 12:
        period = "上午"
    elif 12 <= hour < 14:
        period = "中午"
    elif 14 <= hour < 18:
        period = "下午"
    elif 18 <= hour < 22:
        period = "晚上"
    else:
        period = "深夜"
    return f"现在是{period} {now.strftime('%Y-%m-%d %H:%M')}"


def timestamp() -> str:
    """当前时间 HH:MM"""
    return datetime.now().strftime("%H:%M")


def get_llm_error_message(error: Exception) -> str:
    """将 LLM 异常转为用户友好的中文消息"""
    error_str = str(error).lower()
    if "rate" in error_str or "429" in error_str:
        return "模型太忙了，稍等一下再试~ 🥺"
    elif "auth" in error_str or "401" in error_str or "api_key" in error_str:
        return "API key 好像有问题，检查一下配置哦~"
    elif "timeout" in error_str:
        return "网络有点慢，再试一次？"
    elif "connection" in error_str or "connect" in error_str:
        return "网络好像断了，检查一下网络连接~"
    else:
        return "哎呀，出了点小问题，再试一次？"


# ========== ChatPipeline ==========

class ChatPipeline:
    """消息处理管线：封装从用户输入到 AI 回复的完整编排"""

    def __init__(self, llm, memory_mgr, persona_loader, personality_engine,
                 chat_history, llm_emotion_analyzer, relationship_tracker,
                 mood_manager, config: dict, dialogue_thinker=None,
                 consistency_guard=None, topic_tracker=None, tool_registry=None,
                 open_loop=None, identity=None, life_summary=None,
                 affection_storage: UnifiedAffectionStorage | None = None,
                 brain: BrainCoordinator | None = None):
        self._llm = llm
        self._memory_mgr = memory_mgr
        self._persona_loader = persona_loader
        self._personality_engine = personality_engine
        self._chat_history = chat_history
        self._llm_emotion_analyzer = llm_emotion_analyzer
        self._relationship_tracker = relationship_tracker
        self._affection_storage = affection_storage
        self._mood_engine = mood_manager
        self._personality_engine = personality_engine
        self._tool_registry = tool_registry
        self._dialogue_thinker = dialogue_thinker
        self._topic_tracker = topic_tracker
        self._sticker_replier = None
        self._open_loop = open_loop
        self._identity = identity
        self._life_summary = life_summary
        self._brain = brain
        self._config = config

        # 运行时状态
        self._last_system_prompt = ""
        self._background_tasks: set = set()
        self._last_thought: dict | None = None

        # v1.2：人设一致性检查 & 关系进化
        self._persona_checker = PersonaConsistencyChecker(
            persona_loader=persona_loader,
        )
        self._consistency_guard = ConsistencyGuard()

        # v1.3：人生摘要 / 关系事件 / 人格漂移
        data_dir = memory_mgr.data_dir.parent if hasattr(memory_mgr, 'data_dir') else Path("data")
        self._relationship_events = RelationshipEventTracker(data_dir)
        self._drift_monitor = PersonaDriftMonitor(persona_loader=persona_loader)
        self._conversation_counter: dict[str, int] = {}
        self._last_drift_check: dict[str, int] = {}
        self._last_replies: dict[str, list[str]] = {}

        # v1.3 后台后处理编排器
        self._post_processor = PostProcessOrchestrator(self)

    # ---- 主入口 ----

    async def process(
        self,
        user_id: str,
        content: str,
        persona_id: str,
        on_token: Callable[[str], None] | None = None,
        skip_user_message: bool = False,
    ) -> tuple[str, int]:
        """处理一条用户消息

        Args:
            on_token: 可选的逐 token 回调（流式输出）
            skip_user_message: 跳过用户消息存储（用于 /regen）

        Returns:
            (reply_text, affection_level)
        """
        # ---- 空消息 / 空白消息跳过 ----
        if not content or not content.strip():
            print(f"\033[2m  💬 请输入消息\033[0m")
            current_level = int(self._affection_storage.get_level(user_id, persona_id)) if self._affection_storage else 50
            return "", current_level

        if not self._llm:
            return "我还没配置好模型呢，等等哦~", 50

        persona = self._persona_loader.get(persona_id)
        if not persona:
            return "我找不到我的人设了 (´;ω`)", 50

        # ---- 命令跳过 enrichment ----
        if content.startswith("/"):
            formatted_content, msg_count = format_multi_message(content)
            if not skip_user_message:
                self._chat_history.add_message(user_id, "user", formatted_content)
            messages = self._chat_history.get_messages(user_id)
            time_context = get_time_context()
            memory_context = self._memory_mgr.get_context_prompt(user_id, limit=8, query=content)
            current_level = int(self._affection_storage.get_level(user_id, persona_id)) if self._affection_storage else 50
            system_prompt = PromptBuilder.build(
                persona,
                memory_context=memory_context,
                extra_instructions=f"时间：{time_context}",
                relationship_level=current_level,
            )
            reply = await self._llm_call_with_tools(messages, system_prompt, on_token)
            return reply, current_level

        # 首次使用初始化 LLM 情感分析器
        if self._llm_emotion_analyzer._llm is None:
            self._llm_emotion_analyzer._llm = self._llm

        # 会话开始时加载人格状态（含衰减）
        self._personality_engine.get_state(persona_id)

        # 格式化多消息
        formatted_content, msg_count = format_multi_message(content)

        # ---- [NEW] 亲密度衰减（在 enrichment 之前） ----
        if self._affection_storage:
            self._affection_storage.apply_decay(user_id, persona_id)

        # ---- [MODIFIED] 情感分析（现在是 (EmotionResult, dict) 元组） ----
        # ---- 情感分析：每条消息都经过完整 LLM 分析 ----
        emotion, enriched = await self._llm_emotion_analyzer.analyze(content)

        # ---- Mood 更新 ----
        if self._mood_engine:
            self._mood_engine.update_from_emotion(user_id, emotion)

        # ---- [REPLACED] 人格更新（LLM 驱动，替代旧的硬编码规则） ----
        if self._personality_engine:
            self._personality_engine.update_from_llm(
                user_id,
                affection_impact=enriched.get("affection_impact"),
                personality_shift=enriched.get("personality_shift"),
            )

        # ---- [REPLACED] 亲密度更新（使用 UnifiedAffectionStorage 替代旧的 RelationshipTracker） ----
        affection_impact = enriched.get("affection_impact", {})
        if self._affection_storage:
            rel_level = int(self._affection_storage.update(
                user_id,
                direction=affection_impact.get("direction", "neutral"),
                level=affection_impact.get("level", "low"),
                persona_id=persona_id,
            ))
        else:
            rel_level = self._relationship_tracker.update(
                user_id, emotion=emotion.emotion.value,
                base_level=persona.relationship_level,
                persona_id=persona_id,
            ) if self._relationship_tracker else 50

        # ---- 对话思考 — 分析用户意图，但不注入冗余块到 prompt ----
        self._last_thought = None
        if self._dialogue_thinker:
            try:
                recent_msgs = self._chat_history.get_messages(user_id)[-6:] if not skip_user_message else None
                self._last_thought = await self._dialogue_thinker.think(
                    content, recent_messages=recent_msgs,
                )
            except Exception as e:
                logger.debug(f"Dialogue thinker failed: {e}")

        # 存储用户消息
        if not skip_user_message:
            self._chat_history.add_message(
                user_id, "user", formatted_content,
                emotion=emotion.emotion.value,
                emotion_intensity=emotion.intensity,
                emotion_understanding=enriched.get("emotion_understanding"),
            )

        messages = self._chat_history.get_messages(user_id)

        # 话题追踪
        if not skip_user_message and self._topic_tracker:
            self._topic_tracker.update(content)

        # v1.3 Open Loop: 检测未完成事件
        if self._open_loop and not skip_user_message:
            self._open_loop.detect(user_id, content)

        # v1.3 Identity: 提取身份线索
        if self._identity and not skip_user_message:
            self._identity.extract_from_message(user_id, content)

        # 构建上下文
        time_context = get_time_context()

        # 语义/关键词混合记忆检索
        # 用 thinker 分析到的 topic 增强检索精度
        memory_query = content
        if self._last_thought and self._last_thought.get("topic"):
            memory_query = f"{self._last_thought['topic']} {content}"
        memory_context = self._memory_mgr.get_context_prompt(
            user_id, limit=8, query=memory_query
        )

        # 当嵌入器不可用时，用 LLM 做二次相关性过滤作为补充
        relevant_context = ""
        if not memory_context:
            relevant_memories = await self._retrieve_relevant_memories(user_id, content)
            if relevant_memories:
                relevant_context = "\n【与当前话题相关的记忆】\n" + "\n".join(
                    f"- {m}" for m in relevant_memories
                )

        # ---- Brain: 内心独白（v3.5.1）----
        brain_enabled = self._config.get("brain_enabled", True)
        brain_monologue = None
        if brain_enabled and self._brain:
            try:
                brain_output = await self._brain.run(user_id, persona_id, user_message=content)
                brain_monologue = brain_output.monologue
            except Exception as e:
                logger.warning(f"BrainCoordinator failed: {e}, falling back to flat mode")
                brain_monologue = None

        _brain_active = brain_enabled and bool(brain_monologue)

        # extra_instructions — 精简到真正有价值的信息
        extra_parts = [f"当前时间：{time_context}"]

        # ---- 对话思考：仅注入一行意图提示（非整段分析）----
        if self._last_thought and not _brain_active:
            intent = self._last_thought.get("intent", "")
            if intent in ("撒娇", "抱怨", "倾诉", "表白"):
                extra_parts.append(f"对方似乎在{intent}，注意语气。")

        # ---- Brain 内心独白 ----
        if _brain_active:
            extra_parts.insert(0, brain_monologue)
        else:
            # Mood 风格指令（精简版）
            if self._mood_engine:
                mood_state = self._mood_engine.get_mood(user_id)
                style_hint = MoodExpressionEngine.get_style_instructions(mood_state)
                if style_hint:
                    extra_parts.append(style_hint)

        # 多消息提示
        if msg_count > 1:
            extra_parts.append(
                f"用户一口气发了 {msg_count} 条消息。把它们当整体理解，自然地回应。"
            )

        # ---- 工具描述 ----
        tools_prompt = build_tools_prompt(
            self._tool_registry,
            mcp_manager=getattr(self, '_mcp_manager', None),
        )
        if tools_prompt:
            extra_parts.append(tools_prompt)

        # 话题追踪上下文
        if self._topic_tracker and not _brain_active:
            topic_context = self._topic_tracker.get_topic_context()
            if topic_context:
                extra_parts.append(topic_context)

        if self._tool_registry:
            tool_block = self._tool_registry.get_prompt_block()
            if tool_block:
                extra_parts.append(tool_block)

        extra_combined = "\n\n".join(filter(None, extra_parts))

        # 构建 system prompt
        system_prompt = PromptBuilder.build(
            persona,
            memory_context=memory_context + relevant_context,
            extra_instructions=extra_combined,
            relationship_level=rel_level,
        )
        self._last_system_prompt = system_prompt

        # LLM 调用（含工具循环）
        reply = await self._llm_call_with_tools(messages, system_prompt, on_token)
        if reply.startswith(("模型太忙了", "API key", "网络", "哎呀")):
            return reply, rel_level

        # ---- v1.2：人设一致性检查 ----
        try:
            result = self._persona_checker.check_reply(reply, persona_id)
            if not result.passed:
                logger.warning(f"Persona consistency issues: {result.issues}")
        except Exception as e:
            logger.debug(f"Persona consistency check failed: {e}")

        # ---- 情绪表达增强（v3.5 使用 MoodState 而非 EmotionResult）----
        mood_state_for_emoji = None
        if self._mood_engine:
            mood_state_for_emoji = self._mood_engine.get_mood(user_id)
        reply = EmotionEnhancer.enhance_reply(reply, mood_state=mood_state_for_emoji)

        # ---- 表情包/颜文字增强（v3.5 新增）----
        if self._sticker_replier and mood_state_for_emoji:
            # 从 MoodState 反推 EmotionResult 用于 sticker 选择
            from core.emotion import EmotionResult, EmotionType
            mood_to_etype = {
                "ecstatic": EmotionType.HAPPY, "happy": EmotionType.HAPPY,
                "content": EmotionType.HAPPY, "calm": EmotionType.NEUTRAL,
                "neutral": EmotionType.NEUTRAL, "tired": EmotionType.SAD,
                "sad": EmotionType.SAD, "depressed": EmotionType.SAD,
                "lonely": EmotionType.LONELY, "anxious": EmotionType.ANXIOUS,
                "angry": EmotionType.ANGRY, "frustrated": EmotionType.ANGRY,
                "excited": EmotionType.EXCITED, "love": EmotionType.LOVE,
                "grateful": EmotionType.HAPPY,
            }
            mood_etype = mood_to_etype.get(mood_state_for_emoji.mood.value, EmotionType.NEUTRAL)
            mock_emotion = EmotionResult(emotion=mood_etype, intensity=mood_state_for_emoji.intensity)
            reply = self._sticker_replier.enhance_reply(reply, mock_emotion, rel_level)

        # 保存回复
        self._chat_history.add_message(user_id, "assistant", reply)
        self._chat_history.add_short_memory(user_id, content, reply)

        # 基础记忆存储
        self._memory_mgr.add_memory_sync(user_id, content)

        # 后台任务 — 记忆提取 + 总结
        self._run_background(self._extract_memory(user_id, content, reply))
        threshold = self._config.get("summarize_threshold", 15)
        short_ms = self._chat_history.get_short_memories(user_id)
        if len(short_ms) >= threshold:
            self._run_background(self._summarize_memories(user_id, short_ms))

        # ---- v1.3 后台任务 ----
        self._run_background(self._post_processor.run(user_id, content, reply))

        logger.debug(f"[{persona.name}] → {user_id}: {reply[:80]}...")
        return reply, rel_level

    # ---- LLM 调用（含工具循环）----

    async def _llm_call_with_tools(self, messages, system_prompt, on_token=None) -> str:
        """LLM 调用 + 工具调用循环（委托给 ToolCallHandler）"""
        return await call_llm_with_tools(self, messages, system_prompt, on_token)

    async def _llm_call(self, messages, system_prompt, on_token=None) -> str:
        """流式或非流式 LLM 调用"""
        if on_token:
            try:
                reply_parts = []
                async for token in self._llm.chat_stream(
                    messages=messages, system_prompt=system_prompt
                ):
                    on_token(token)
                    reply_parts.append(token)
                return "".join(reply_parts)
            except Exception as e:
                logger.error(f"LLM stream failed: {e}")
                return get_llm_error_message(e)

        try:
            response = await self._llm.chat(
                messages=messages, system_prompt=system_prompt
            )
            return response.content
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return get_llm_error_message(e)

    # ---- system prompt 读取 ----

    def get_last_system_prompt(self) -> str:
        """供 /debug 命令查看"""
        return self._last_system_prompt

    # ---- 后台任务 ----

    def _run_background(self, coro):
        """启动后台协程，保持引用防止 GC"""
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _retrieve_relevant_memories(self, user_id: str, query: str) -> list[str]:
        """LLM 检索相关记忆"""
        try:
            all_ms = self._memory_mgr.get_memories(user_id, limit=30)
            if not all_ms:
                return []
            texts = [m.content for m in all_ms]
            summarizer = MemorySummarizer(self._llm)
            result = await summarizer.retrieve_relevant(query, texts, limit=3)
            return result or []
        except Exception as e:
            logger.debug(f"Memory retrieval failed: {e}")
            return []

    async def _extract_memory(self, user_id: str, user_msg: str, assistant_reply: str):
        """后台提取值得记住的信息"""
        try:
            summarizer = MemorySummarizer(self._llm)
            extracted = await summarizer.extract_memory(user_msg, assistant_reply)
            if extracted and extracted.get("content"):
                content = extracted["content"]
                importance = extracted.get("importance", 3)
                if importance >= 2:
                    self._memory_mgr.add_memory(
                        user_id, content, level=importance, tags=["自动提取"]
                    )
                    logger.info(
                        f"Auto-extracted memory [{importance}★]: {content[:30]}..."
                    )
        except Exception as e:
            logger.debug(f"Background memory extraction failed: {e}")

    async def _summarize_memories(self, user_id: str, short_memories: list):
        """后台总结短期记忆"""
        try:
            summarizer = MemorySummarizer(self._llm)
            summary = await summarizer.summarize(short_memories)
            if summary:
                self._memory_mgr.add_memory(user_id, summary, level=4, tags=["总结"])
                self._chat_history.clear_short_memories(user_id)
                logger.info(f"Short memory summarized for {user_id}")
        except Exception as e:
            logger.warning(f"Background summarization failed: {e}")
