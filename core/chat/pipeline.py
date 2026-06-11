"""ChatPipeline — 消息处理管线

从用户消息到 AI 回复的完整流程：
  情绪分析 → 记忆检索（向量/关键词）→ Prompt构建 → LLM调用
  → 记忆保存（含向量索引）→ 后台 LLM 提取+总结

用法:
    pipeline = ChatPipeline(llm, memory_mgr, persona_loader, chat_history,
                            llm_emotion_analyzer, relationship_tracker, config)
    reply, level = await pipeline.process(user_id, content, persona_id)
"""

import asyncio
from collections.abc import Callable
from datetime import datetime

from loguru import logger

from core.emotion import EmotionEnhancer
from core.memory import MemorySummarizer
from core.persona import PromptBuilder


# ========== 模块级工具函数（可独立测试）==========

def format_multi_message(content: str) -> tuple[str, int]:
    """将多行消息格式化为 [消息1]/[消息2]... 格式

    Returns:
        (formatted_content, message_count) 元组
    """
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

    def __init__(self, llm, memory_mgr, persona_loader, chat_history,
                 llm_emotion_analyzer, relationship_tracker, config: dict):
        self._llm = llm
        self._memory_mgr = memory_mgr
        self._persona_loader = persona_loader
        self._chat_history = chat_history
        self._llm_emotion_analyzer = llm_emotion_analyzer
        self._relationship_tracker = relationship_tracker
        self._config = config

        # 运行时状态
        self._last_system_prompt = ""
        self._background_tasks: set = set()

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
            (reply_text, relationship_level)
        """
        if not self._llm:
            return "我还没配置好模型呢，等等哦~", 50

        persona = self._persona_loader.get(persona_id)
        if not persona:
            return "我找不到我的人设了 (´;ω`)", 50

        # 首次使用初始化 LLM 情感分析器
        if self._llm_emotion_analyzer._llm is None:
            self._llm_emotion_analyzer._llm = self._llm

        # 格式化多消息
        formatted_content, msg_count = format_multi_message(content)

        # 情感分析（必须在 add_message 之前）
        emotion = await self._llm_emotion_analyzer.analyze(content)

        # 存储用户消息
        if not skip_user_message:
            self._chat_history.add_message(
                user_id, "user", formatted_content,
                emotion=emotion.emotion.value,
                emotion_intensity=emotion.intensity,
            )

        messages = self._chat_history.get_messages(user_id)

        # 更新亲密度
        rel_level = self._relationship_tracker.update(
            user_id, emotion=emotion.emotion.value,
            base_level=persona.relationship_level,
            persona_id=persona_id,
        )

        # 构建上下文
        time_context = get_time_context()

        # 语义/关键词混合记忆检索：传 query 则优先向量搜索，否则按重要度
        memory_context = self._memory_mgr.get_context_prompt(
            user_id, limit=8, query=content
        )

        # 当嵌入器不可用时，用 LLM 做二次相关性过滤作为补充
        relevant_context = ""
        if not memory_context:
            relevant_memories = await self._retrieve_relevant_memories(user_id, content)
            if relevant_memories:
                relevant_context = "\n【与当前话题相关的记忆】\n" + "\n".join(
                    f"- {m}" for m in relevant_memories
                )

        # extra_instructions：多消息时增加上下文说明
        extra = (
            f"时间：{time_context}\n"
            f"用户当前情绪：{emotion.emotion.value}（强度 {emotion.intensity}）"
        )
        if msg_count > 1:
            extra += (
                f"\n【重要】用户连续发了 {msg_count} 条消息，这是用户在短时间内快速输入的碎片化想法。"
                f"请把它们作为一个整体来理解用户的情绪和意图，"
                f"回复时自然地回应所有内容，不要逐条回复，也不要提到「你发了很多消息」之类的话。"
                f"像真人聊天一样，抓住重点，整体回应。"
            )

        # 构建 system prompt
        system_prompt = PromptBuilder.build(
            persona,
            memory_context=memory_context + relevant_context,
            extra_instructions=extra,
            relationship_level=rel_level,
        )
        self._last_system_prompt = system_prompt

        # LLM 调用
        reply = await self._llm_call(messages, system_prompt, on_token)
        if reply.startswith(("模型太忙了", "API key", "网络", "哎呀")):
            return reply, rel_level

        # 情感增强
        reply = EmotionEnhancer.enhance_reply(reply, emotion)

        # 保存回复
        self._chat_history.add_message(user_id, "assistant", reply)
        self._chat_history.add_short_memory(user_id, content, reply)

        # 基础记忆存储（关键词评分）
        self._memory_mgr.add_memory(user_id, content)

        # 后台任务
        self._run_background(self._extract_memory(user_id, content, reply))
        threshold = self._config.get("summarize_threshold", 15)
        short_ms = self._chat_history.get_short_memories(user_id)
        if len(short_ms) >= threshold:
            self._run_background(self._summarize_memories(user_id, short_ms))

        logger.debug(f"[{persona.name}] → {user_id}: {reply[:80]}...")
        return reply, rel_level

    # ---- LLM 调用 ----

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
