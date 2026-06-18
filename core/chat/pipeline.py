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
import json
import re
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
from core.open_loop import OpenLoopEngine
from core.identity import IdentityStorage
from core.summary import LifeSummaryEngine
from core.social.relationship.events import RelationshipEventTracker
from core.persona.drift_monitor import PersonaDriftMonitor
from core.social.affection.storage import UnifiedAffectionStorage


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


# 工具调用正则：从 LLM 回复中解析工具调用
# 格式：【工具调用：工具名(参数名="值", 参数名2="值2")】
_TOOL_CALL_PATTERN = re.compile(r'【工具调用：(\w+)\(([^)]*)\)】')


def _parse_tool_call(text: str) -> list[tuple[str, dict[str, str]]]:
    """从 LLM 回复中解析工具调用

    Returns:
        [(tool_name, {param: value}), ...]
    """
    results = []
    for match in _TOOL_CALL_PATTERN.finditer(text):
        name = match.group(1)
        params_str = match.group(2)
        params: dict[str, str] = {}
        if params_str.strip():
            # 解析 key="value" 或 key='value' 格式的参数
            for param_match in re.finditer(r'(\w+)\s*=\s*["\']([^"\']*)["\']', params_str):
                params[param_match.group(1)] = param_match.group(2)
        results.append((name, params))
    return results


def _build_tools_prompt(tool_registry) -> str:
    """构建工具描述 prompt，告诉 LLM 可用的工具"""
    if not tool_registry or not tool_registry.available:
        return ""

    lines = [
        "你有以下工具可以使用。当用户需要相关信息时，你可以调用工具来获取。",
        "调用格式：【工具调用：工具名(参数名=\"值\")】",
        "注意：一次只能调用一个工具。工具结果会自动呈现给你。",
        "",
        "可用工具：",
    ]
    for tool in tool_registry.list_tools():
        params = tool.parameters
        props = params.get("properties", {})
        param_desc = []
        for pname, pinfo in props.items():
            required = "（必填）" if pname in params.get("required", []) else "（可选）"
            desc = pinfo.get("description", "")
            param_desc.append(f"    - {pname}: {desc} {required}")
        param_str = "\n".join(param_desc) if param_desc else "    无参数"
        lines.append(f"\n- {tool.name}：{tool.description}")
        lines.append(param_str)

    lines.extend([
        "",
        "示例：如果用户问「今天几号」，你可以调用：",
        "【工具调用：get_current_time(format='date')】",
        "等待工具返回结果后，把结果告诉用户即可。",
    ])
    return "\n".join(lines)


# ========== ChatPipeline ==========

class ChatPipeline:
    """消息处理管线：封装从用户输入到 AI 回复的完整编排"""

    def __init__(self, llm, memory_mgr, persona_loader, personality_engine,
                 chat_history, llm_emotion_analyzer, relationship_tracker,
                 mood_manager, config: dict, dialogue_thinker=None,
                 consistency_guard=None, topic_tracker=None, tool_registry=None,
                 open_loop=None, identity=None, life_summary=None,
                 affection_storage: UnifiedAffectionStorage | None = None):
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

        # v1.3：身份层 / Open Loop / 人生摘要 / 关系事件 / 人格漂移
        data_dir = memory_mgr.data_dir.parent if hasattr(memory_mgr, 'data_dir') else Path("data")
        self._identity_storage = IdentityStorage(data_dir)
        self._open_loop_engine = OpenLoopEngine(data_dir)
        self._life_summary_engine = LifeSummaryEngine(data_dir)
        self._relationship_events = RelationshipEventTracker(data_dir)
        self._drift_monitor = PersonaDriftMonitor(persona_loader=persona_loader)
        self._conversation_counter: dict[str, int] = {}
        self._last_drift_check: dict[str, int] = {}
        self._last_replies: dict[str, list[str]] = {}

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

        # ---- 对话思考（v3.5）— 在 prompt 构建前分析用户意图 ----
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

        # 对话思考
        if self._dialogue_thinker:
            thought = await self._dialogue_thinker.think(
                content, recent_messages=messages[-6:] if messages else None
            )
        else:
            thought = self._last_thought

        # 构建上下文
        time_context = get_time_context()

        # 语义/关键词混合记忆检索
        memory_context = self._memory_mgr.get_context_prompt(
            user_id, limit=8, query=content
        )

        # v1.3 新增上下文层
        open_loop_context = ""
        if self._open_loop:
            open_loop_context = self._open_loop.get_context(user_id)

        identity_context = ""
        if self._identity:
            identity_context = self._identity.get_context(user_id)

        life_summary_context = ""
        if self._life_summary:
            life_summary_context = self._life_summary.get_context(user_id)

        # 当嵌入器不可用时，用 LLM 做二次相关性过滤作为补充
        relevant_context = ""
        if not memory_context:
            relevant_memories = await self._retrieve_relevant_memories(user_id, content)
            if relevant_memories:
                relevant_context = "\n【与当前话题相关的记忆】\n" + "\n".join(
                    f"- {m}" for m in relevant_memories
                )

        # extra_instructions：包含 mood 风格/思考/人格/工具上下文
        extra_parts = [f"时间：{time_context}\n用户当前情绪：{emotion.emotion.value}（强度 {emotion.intensity}）"]

        # ---- Mood 表达风格指令（v3.5）----
        if self._mood_engine:
            mood_state = self._mood_engine.get_mood(user_id)
            style_instructions = MoodExpressionEngine.get_style_instructions(mood_state)
            extra_parts.append(style_instructions)
            energy_bar = MoodExpressionEngine.get_energy_bar(mood_state.energy)
            extra_parts.append(f"你的精力：{energy_bar}")

        # ---- 对话思考结果注入（v3.5）----
        if self._last_thought and self._dialogue_thinker:
            thought_instruction = DialogueThinker.format_thought_as_instruction(self._last_thought)
            if thought_instruction:
                extra_parts.append(thought_instruction)

        # ---- 人格上下文 ----
        if self._personality_engine:
            personality_context = self._personality_engine.get_personality_context(user_id)
            extra_parts.append(personality_context)

        # 多消息提示
        if msg_count > 1:
            extra_parts.append(
                f"【重要】用户连续发了 {msg_count} 条消息，这是用户在短时间内快速输入的碎片化想法。"
                f"请把它们作为一个整体来理解用户的情绪和意图，"
                f"回复时自然地回应所有内容，不要逐条回复，也不要提到「你发了很多消息」之类的话。"
                f"像真人聊天一样，抓住重点，整体回应。"
            )

        # ---- 工具描述（新增）----
        tools_prompt = _build_tools_prompt(self._tool_registry)
        if tools_prompt:
            extra_parts.append(tools_prompt)

        # ---- v1.3：Open Loop 检测 + Identity 提取 ----
        try:
            self._open_loop_engine.detect_and_create(user_id, content)
            self._open_loop_engine.check_and_update(user_id, content)
            self._open_loop_engine.check_expired(user_id)
        except Exception as e:
            logger.debug(f"OpenLoop processing failed: {e}")

        try:
            self._identity_storage.extract_from_content(user_id, content)
        except Exception as e:
            logger.debug(f"Identity extraction failed: {e}")

        # 话题追踪上下文
        topic_context = ""
        if self._topic_tracker:
            topic_context = self._topic_tracker.get_topic_context()

        # 合并额外指令
        extra_parts.append(topic_context) if topic_context else None
        extra_parts.append(open_loop_context) if open_loop_context else None
        extra_parts.append(identity_context) if identity_context else None
        extra_parts.append(life_summary_context) if life_summary_context else None
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
        self._run_background(self._v13_post_process(user_id, content, reply))

        logger.debug(f"[{persona.name}] → {user_id}: {reply[:80]}...")
        return reply, rel_level

    # ---- v1.3 后台处理 ----

    async def _v13_post_process(self, user_id: str, content: str, reply: str):
        """v1.3 后台处理：关系事件/人生摘要/对话计数/漂移检测"""
        try:
            # 1. 关系事件
            self._relationship_events.detect_and_record(user_id, content, reply)

            # 2. 对话计数
            self._conversation_counter[user_id] = self._conversation_counter.get(user_id, 0) + 1
            conv_count = self._conversation_counter[user_id]

            # 3. 收集回复用于漂移检测
            if user_id not in self._last_replies:
                self._last_replies[user_id] = []
            self._last_replies[user_id].append(reply)
            if len(self._last_replies[user_id]) > 50:
                self._last_replies[user_id] = self._last_replies[user_id][-50:]

            # 4. 人生摘要生成
            try:
                if self._life_summary_engine.should_generate(user_id, conv_count):
                    all_memories = self._memory_mgr.get_memories(user_id, limit=50)
                    memory_texts = [m.content for m in all_memories if m.content]
                    self._life_summary_engine.generate_from_memories(
                        user_id, conv_count, memory_texts
                    )
            except Exception as e:
                logger.debug(f"LifeSummary generation failed: {e}")

            # 5. 人格漂移检测
            try:
                last_check = self._last_drift_check.get(user_id, 0)
                if self._drift_monitor.should_check(conv_count, last_check):
                    persona_id = "girlfriend_001"
                    recent = self._last_replies.get(user_id, [])
                    report = self._drift_monitor.analyze(
                        user_id, persona_id, conv_count, recent[-20:]
                    )
                    self._last_drift_check[user_id] = conv_count
                    if not report.passed:
                        logger.warning(
                            f"Persona drift: score={report.consistency_score:.2%}, "
                            f"suggestions={report.suggestions}"
                        )
            except Exception as e:
                logger.debug(f"Persona drift check failed: {e}")

        except Exception as e:
            logger.debug(f"v1.3 post-process failed: {e}")

    # ---- LLM 调用（含工具循环）----

    async def _llm_call_with_tools(self, messages, system_prompt, on_token=None) -> str:
        """LLM 调用 + 工具调用循环

        如果 LLM 回复中包含工具调用，执行工具并将结果喂回，
        最多进行 1 轮工具调用（防止无限循环）。
        """
        if not self._tool_registry or not self._tool_registry.available:
            # 没有工具，走标准调用
            return await self._llm_call(messages, system_prompt, on_token)

        # 第一轮调用
        reply = await self._llm_call(messages, system_prompt, on_token)

        # 检查是否有工具调用
        tool_calls = _parse_tool_call(reply)
        if not tool_calls:
            return reply

        # 只处理第一个工具调用（避免多工具复杂度）
        tool_name, params = tool_calls[0]
        tool = self._tool_registry.get(tool_name)
        if not tool:
            logger.warning(f"Unknown tool called: {tool_name}")
            return reply

        logger.info(f"Tool call: {tool_name}({params})")

        # 执行工具
        try:
            result = await tool.execute(**params)
        except Exception as e:
            result = type("Result", (), {"output": f"工具执行失败：{e}", "success": False})()

        if result.success:
            tool_feedback = (
                f"\n\n【工具 {tool_name} 执行结果】\n{result.output}\n"
                f"请根据以上信息，自然地回复用户。如果结果是数据，直接告诉用户即可。"
                f"不要提及「工具」或「调用」等词。"
            )
        else:
            tool_feedback = (
                f"\n\n【工具 {tool_name} 执行失败】\n{result.output}\n"
                f"请告诉用户暂时无法提供这个信息，说点别的。"
            )

        # 如果原来是流式输出，工具调用后会走非流式
        return await self._llm_call(messages, system_prompt + tool_feedback, on_token=None)

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
