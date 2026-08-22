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
import random
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from time import monotonic

from loguru import logger

from core.config import parse_uid
from core.emotion import EmotionEnhancer
from core.dialogue import PersonaConsistencyChecker, ConsistencyGuard, DialogueThinker, TopicTracker
from core.memory import MemorySummarizer
from core.persona import PromptBuilder
from core.social.relationship.events import RelationshipEventTracker
from core.persona.drift_monitor import PersonaDriftMonitor
from core.social.affection.storage import UnifiedAffectionStorage
from core.brain import BrainCoordinator
from core.chat.tool_handler import call_llm_with_tools
from core.chat.context_builder import (
    PromptContextAssembler,
    get_time_context,
    insert_dynamic_context,
)
from core.chat.enrichment import MessageEnricher
from core.chat.post_process import PostProcessOrchestrator
from core.runtime import BackgroundTaskManager, runtime_metrics
from core.llm.base import LLMResponse


# ========== 模块级工具函数（可独立测试）==========

def format_multi_message(content: str) -> tuple[str, int]:
    """将多行消息格式化为 [消息1]/[消息2]... 格式"""
    lines = [line.strip() for line in content.split("\n") if line.strip()]
    if len(lines) <= 1:
        return content, 1
    formatted = "\n".join(f"[消息{i}] {line}" for i, line in enumerate(lines, 1))
    return formatted, len(lines)


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
        self._sticker_service = None
        self._open_loop = open_loop
        self._identity = identity
        self._life_summary = life_summary
        self._brain = brain
        self._config = config

        # 运行时状态
        self._last_system_prompt = ""
        self._tasks = BackgroundTaskManager()
        self._last_thought: dict | None = None

        # v1.2：人设一致性检查 & 关系进化
        self._persona_checker = PersonaConsistencyChecker(
            persona_loader=persona_loader,
        )
        self._consistency_guard = ConsistencyGuard()

        # v1.3：人生摘要 / 关系事件 / 人格漂移
        data_dir = memory_mgr.data_dir if hasattr(memory_mgr, 'data_dir') else Path("data")
        self._relationship_events = RelationshipEventTracker(data_dir)
        self._drift_monitor = PersonaDriftMonitor(persona_loader=persona_loader)
        self._enricher = MessageEnricher(
            llm=llm,
            emotion_analyzer=llm_emotion_analyzer,
            mood_engine=mood_manager,
            personality_engine=personality_engine,
            affection_storage=affection_storage,
            relationship_tracker=relationship_tracker,
            dialogue_thinker=dialogue_thinker,
            chat_history=chat_history,
        )
        self._context_assembler = PromptContextAssembler(
            memory_manager=memory_mgr,
            mood_engine=mood_manager,
            topic_tracker=topic_tracker,
            tool_registry=tool_registry,
            brain=brain,
            config=config,
        )
        self._post_processor = PostProcessOrchestrator(
            memory_manager=memory_mgr,
            life_summary=life_summary,
            persona_loader=persona_loader,
            affection_storage=affection_storage,
            chat_history=chat_history,
            relationship_events=self._relationship_events,
            drift_monitor=self._drift_monitor,
        )

    def set_llm(self, llm) -> None:
        """Activate or replace the runtime model without rebuilding user state."""
        self._llm = llm
        self._enricher._llm = llm
        if self._dialogue_thinker is None:
            self._dialogue_thinker = DialogueThinker(llm=llm)
        else:
            self._dialogue_thinker.set_llm(llm)
        self._enricher._dialogue_thinker = self._dialogue_thinker
        self._consistency_guard.set_llm(llm)
        if self._topic_tracker is None:
            self._topic_tracker = TopicTracker()
            self._context_assembler._topic_tracker = self._topic_tracker

    # ---- 主入口 ----

    async def process(
        self,
        user_id: str,
        content: str,
        persona_id: str,
        on_token: Callable[[str], None] | None = None,
        skip_user_message: bool = False,
        on_event: Callable[[str, dict], None] | None = None,
        sticker: dict | None = None,
        scope_id: str | None = None,
    ) -> tuple[str, int]:
        """处理一条用户消息

        Args:
            on_token: 可选的逐 token 回调（流式输出）
            skip_user_message: 跳过用户消息存储（用于 /regen）
            scope_id: 绑定会话的记忆作用域；为空时保留旧版 user_id 行为

        Returns:
            (reply_text, affection_level)
        """
        # 复合 user_id 解析（T5）：提取 platform/account_id 传给 chat_history
        parsed_uid = parse_uid(user_id)
        # Adapter routing uses the external user_id, while all stateful memory
        # stores use the bound conversation/persona scope when one is supplied.
        memory_user_id = scope_id or user_id
        # ---- 空消息 / 空白消息跳过 ----
        if not content or not content.strip():
            print(f"\033[2m  💬 请输入消息\033[0m")
            current_level = int(self._affection_storage.get_level(memory_user_id, persona_id)) if self._affection_storage else 50
            return "", current_level

        if not self._llm:
            return "我还没配置好模型呢，等等哦~", 50

        persona = self._persona_loader.get(persona_id)
        if on_event:
            on_event("phase", {"name": "context", "label": "整理上下文"})
        if not persona:
            return "我找不到我的人设了 (´;ω`)", 50

        # ---- 命令跳过 enrichment ----
        if content.startswith("/"):
            formatted_content, msg_count = format_multi_message(content)
            if not skip_user_message:
                self._chat_history.add_message(
                    memory_user_id, "user", formatted_content,
                    platform=parsed_uid["platform"],
                    persona_id=persona_id,
                    account_id=parsed_uid["account_id"],
                    sticker=sticker,
                )
            messages = self._chat_history.get_messages(memory_user_id)
            time_context = get_time_context()
            memory_context = self._memory_mgr.get_context_prompt(memory_user_id, limit=8, query=content)
            current_level = int(self._affection_storage.get_level(memory_user_id, persona_id)) if self._affection_storage else 50
            stable_prompt = PromptBuilder.build_stable(persona)
            dynamic_context = PromptBuilder.build_dynamic_context(
                persona,
                memory_context=memory_context,
                extra_instructions=f"时间：{time_context}",
                relationship_level=current_level,
            )
            request_messages = insert_dynamic_context(messages, dynamic_context)
            self._last_system_prompt = "\n\n".join((stable_prompt, dynamic_context))
            reply = await self._llm_call_with_tools(
                request_messages, stable_prompt, on_token, on_event,
            )
            return reply, current_level

        formatted_content, msg_count = format_multi_message(content)
        preview = self._enricher.preview(memory_user_id, content, persona_id)
        emotion = preview.emotion
        enriched = preview.details
        rel_level = preview.relationship_level
        self._last_thought = None

        # Store immediately with the local preview. The richer analysis runs in
        # parallel with prompt assembly and the user-visible model response.
        if not skip_user_message:
            self._chat_history.add_message(
                memory_user_id, "user", formatted_content,
                emotion=emotion.emotion.value,
                emotion_intensity=emotion.intensity,
                emotion_understanding=enriched.get("emotion_understanding"),
                platform=parsed_uid["platform"],
                persona_id=persona_id,
                account_id=parsed_uid["account_id"],
                sticker=sticker,
            )

        messages = self._chat_history.get_messages(memory_user_id)

        # Topic/identity extraction is local and can proceed while enrichment runs.
        if not skip_user_message and self._topic_tracker:
            self._topic_tracker.update(content)
        if self._open_loop and not skip_user_message:
            self._open_loop.detect(memory_user_id, content)
        if self._identity and not skip_user_message:
            self._identity.extract_from_message(memory_user_id, content)

        self._context_assembler.mcp_manager = getattr(self, "_mcp_manager", None)
        prompt_context = await self._context_assembler.build(
            user_id=memory_user_id,
            persona_id=persona_id,
            persona=persona,
            content=content,
            messages=messages,
            relationship_level=rel_level,
            message_count=msg_count,
            thought=None,
            retrieve_fallback=self._retrieve_relevant_memories,
        )
        stable_prompt = prompt_context.stable_prompt
        request_messages = prompt_context.request_messages
        self._last_system_prompt = "\n\n".join(
            (stable_prompt, prompt_context.dynamic_context)
        )

        # LLM 调用（含工具循环 + 错误隔离）
        async def _generate_reply() -> str:
            started = monotonic()
            try:
                if on_event:
                    on_event("phase", {"name": "thinking", "label": "正在思考"})
                reply_text = await self._llm_call_with_tools(
                    request_messages, stable_prompt, on_token, on_event,
                )
                runtime_metrics.record(
                    "pipeline.reply", (monotonic() - started) * 1000,
                )
                return reply_text
            except Exception as e:
                runtime_metrics.record(
                    "pipeline.reply", (monotonic() - started) * 1000,
                    success=False,
                )
                logger.error(f"Main LLM call failed: {e}")
                return get_llm_error_message(e)

        # Dispatch the user-visible request first, then auxiliary analysis on
        # the next scheduler slot. Both remote calls overlap, while adapters
        # that are sensitive to request ordering keep the main response first.
        reply_task = asyncio.create_task(
            _generate_reply(), name=f"reply:{user_id}",
        )
        enrichment_task = self._tasks.create(
            self._analyze_and_apply_enrichment(
                memory_user_id,
                content,
                persona_id,
                persona,
                skip_user_message=skip_user_message,
            ),
            name=f"enrich:{memory_user_id}",
        )
        reply = await reply_task
        # Drain only work that is already runnable. Nested gather/tasks need a
        # few scheduler turns; none of these yields waits for network I/O.
        for _ in range(4):
            if enrichment_task is None or enrichment_task.done():
                break
            await asyncio.sleep(0)
        if enrichment_task is not None and enrichment_task.done():
            try:
                rel_level = await enrichment_task
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.debug(f"Concurrent enrichment failed: {e}")
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
        sticker_meta = None
        if self._mood_engine:
            mood_state_for_emoji = self._mood_engine.get_mood(memory_user_id)
        reply = EmotionEnhancer.enhance_reply(reply, mood_state=mood_state_for_emoji)

        # Image stickers are optional presentation metadata. They never enter
        # the model context and are selected locally from the current mood.
        if (
            self._sticker_service is not None
            and getattr(persona, "sticker_enabled", True)
            and random.random() < float(getattr(persona, "sticker_probability", 0.18) or 0)
        ):
            mood_name = getattr(getattr(mood_state_for_emoji, "mood", None), "value", "neutral")
            try:
                sticker_meta = self._sticker_service.choose(
                    mood_name, pack=getattr(persona, "sticker_pack", "builtin") or "builtin",
                )
            except Exception as exc:
                logger.debug(f"Sticker selection skipped: {exc}")
            if sticker_meta and on_event:
                on_event("sticker", sticker_meta)

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
        self._chat_history.add_message(
            memory_user_id, "assistant", reply,
            platform=parsed_uid["platform"],
            persona_id=persona_id,
            account_id=parsed_uid["account_id"],
            sticker=sticker_meta,
        )
        self._chat_history.add_short_memory(memory_user_id, content, reply)

        # 基础记忆存储
        self._memory_mgr.add_memory_sync(memory_user_id, content)

        # 后台任务 — 记忆提取（有开关 + 短消息跳过）
        auto_extract = self._config.get("auto_extract_memory", True)
        if auto_extract and len(content) > 10:
            self._run_background(self._extract_memory(memory_user_id, content, reply))
        threshold = self._config.get("summarize_threshold", 15)
        short_ms = self._chat_history.get_short_memories(memory_user_id)
        if len(short_ms) >= threshold:
            self._run_background(self._summarize_memories(memory_user_id, short_ms))

        # ---- v1.3 后台任务 ----
        self._run_background(
            self._post_processor.run(memory_user_id, content, reply, persona_id)
        )

        # Auxiliary work may have completed during local post-processing. Read
        # its result without blocking so fast analyses keep the legacy level.
        if enrichment_task is not None and enrichment_task.done():
            try:
                rel_level = enrichment_task.result()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.debug(f"Concurrent enrichment failed: {e}")

        logger.debug(f"[{persona.name}] → {user_id}: {reply[:80]}...")
        return reply, rel_level

    # ---- LLM 调用（含工具循环）----

    async def _llm_call_with_tools(
        self, messages, system_prompt, on_token=None, on_event=None,
    ) -> str:
        """LLM 调用 + 工具调用循环（委托给 ToolCallHandler）"""
        return await call_llm_with_tools(
            self, messages, system_prompt, on_token, on_event,
        )

    async def _llm_call(
        self, messages, system_prompt, on_token=None, on_event=None,
    ) -> str:
        """流式或非流式 LLM 调用"""
        try:
            response = await self._llm_call_response(
                messages, system_prompt, on_token, on_event=on_event,
            )
            return response.content
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return get_llm_error_message(e)

    async def _llm_call_response(
        self,
        messages,
        system_prompt,
        on_token=None,
        tools: list[dict] | None = None,
        on_event=None,
    ) -> LLMResponse:
        """Return normalized content and native tool-call metadata."""
        if on_token:
            if hasattr(self._llm, "chat_stream_events"):
                reply_parts: list[str] = []
                tool_calls: list[dict] = []
                reply_phase_emitted = False
                event_kwargs = {}
                if tools:
                    event_kwargs.update({"tools": tools, "tool_choice": "auto"})
                async for event in self._llm.chat_stream_events(
                    messages=messages,
                    system_prompt=system_prompt,
                    **event_kwargs,
                ):
                    if event.kind == "content":
                        if on_event and not reply_phase_emitted:
                            on_event("phase", {"name": "reply", "label": "生成回复"})
                            reply_phase_emitted = True
                        reply_parts.append(event.content)
                        if on_token:
                            on_token(event.content)
                    elif event.kind == "reasoning":
                        if on_event:
                            on_event("reasoning", {"text": event.reasoning})
                    elif event.kind == "tool_call" and event.tool_call:
                        tool_calls.append(event.tool_call)
                return LLMResponse(
                    content="".join(reply_parts),
                    model=getattr(self._llm, "model_name", ""),
                    metadata={"tool_calls": tool_calls},
                )

            reply_parts = []
            if on_event:
                on_event("phase", {"name": "reply", "label": "生成回复"})
            async for token in self._llm.chat_stream(
                messages=messages, system_prompt=system_prompt
            ):
                on_token(token)
                if on_event:
                    on_event("content", {"text": token})
                reply_parts.append(token)
            return LLMResponse(
                content="".join(reply_parts),
                model=getattr(self._llm, "model_name", ""),
            )

        call_kwargs = {}
        if tools:
            call_kwargs.update({"tools": tools, "tool_choice": "auto"})
        return await self._llm.chat(
            messages=messages,
            system_prompt=system_prompt,
            **call_kwargs,
        )

    # ---- system prompt 读取 ----

    def get_last_system_prompt(self) -> str:
        """供 /debug 命令查看"""
        return self._last_system_prompt

    # ---- 后台任务 ----

    def _run_background(self, coro):
        """Schedule bounded background work through the shared lifecycle manager."""
        self._tasks.create(coro)

    async def _analyze_and_apply_enrichment(
        self,
        user_id: str,
        content: str,
        persona_id: str,
        persona,
        *,
        skip_user_message: bool,
    ) -> int:
        """Analyze and commit auxiliary state independently of reply latency."""
        started = monotonic()
        try:
            enrichment = await self._enricher.analyze(
                user_id,
                content,
                persona_id,
                persona,
                skip_user_message=skip_user_message,
            )
            self._last_thought = enrichment.thought
            result = self._enricher.apply(
                user_id, persona_id, persona, enrichment,
            )
            runtime_metrics.record(
                "pipeline.enrichment", (monotonic() - started) * 1000,
            )
            return result
        except asyncio.CancelledError:
            raise
        except Exception:
            runtime_metrics.record(
                "pipeline.enrichment", (monotonic() - started) * 1000,
                success=False,
            )
            raise

    async def shutdown(self) -> None:
        """Cancel and await background work before the application exits."""
        await self._tasks.shutdown()

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
                    await self._memory_mgr.add_memory(
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
                await self._memory_mgr.add_memory(user_id, summary, level=4, tags=["总结"])
                self._chat_history.clear_short_memories(user_id)
                logger.info(f"Short memory summarized for {user_id}")
        except Exception as e:
            logger.warning(f"Background summarization failed: {e}")
