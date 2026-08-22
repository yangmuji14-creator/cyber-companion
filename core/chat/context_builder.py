"""Prompt and request-context assembly for the chat pipeline."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

from loguru import logger

from core.chat.tool_handler import build_tools_prompt
from core.emotion import MoodExpressionEngine
from core.persona import PromptBuilder, build_fused_style


DEFAULT_CONTEXT_CHAR_BUDGET = 24_000


def _llm_message(message: dict) -> dict:
    """Strip UI-only metadata (sticker, timestamps, emotion) before provider calls."""
    return {
        key: value for key, value in message.items()
        if key in {"role", "content", "name", "tool_calls", "tool_call_id"}
    }


def trim_messages_to_budget(
    messages: list[dict[str, str]],
    *,
    max_chars: int,
    reserved_chars: int = 0,
) -> list[dict[str, str]]:
    """Keep the current request and newest complete turns within a char budget.

    This trims only the request copy sent to the model. Persisted history is not
    modified. Character budgeting is provider-independent and deliberately
    conservative for mixed Chinese/English prompts.
    """
    if not messages:
        return []
    available = max(0, max_chars - max(0, reserved_chars))
    current_user = next(
        (index for index in range(len(messages) - 1, -1, -1)
         if messages[index].get("role") == "user"),
        len(messages) - 1,
    )
    required_start = current_user
    while required_start > 0 and messages[required_start - 1].get("role") == "system":
        required_start -= 1

    selected = [_llm_message(message) for message in messages[required_start:]]
    used = sum(len(str(message.get("content", ""))) for message in selected)
    cursor = required_start - 1
    groups: list[list[dict[str, str]]] = []
    while cursor >= 0:
        start = cursor
        if messages[cursor].get("role") == "assistant":
            if cursor > 0 and messages[cursor - 1].get("role") == "user":
                start = cursor - 1
        groups.append([_llm_message(message) for message in messages[start:cursor + 1]])
        cursor = start - 1

    kept_groups: list[list[dict[str, str]]] = []
    for group in groups:
        size = sum(len(str(message.get("content", ""))) for message in group)
        if used + size > available:
            break
        kept_groups.append(group)
        used += size
    prefix = [message for group in reversed(kept_groups) for message in group]
    return [*prefix, *selected]


def get_time_context() -> str:
    now = datetime.now()
    hour = now.hour
    if hour < 6:
        period = "深夜"
    elif hour < 9:
        period = "早上"
    elif hour < 12:
        period = "上午"
    elif hour < 14:
        period = "中午"
    elif hour < 18:
        period = "下午"
    elif hour < 22:
        period = "晚上"
    else:
        period = "深夜"
    return f"现在是{period} {now:%Y-%m-%d %H:%M}"


def insert_dynamic_context(
    messages: list[dict[str, str]],
    dynamic_context: str,
) -> list[dict[str, str]]:
    request_messages = [_llm_message(message) for message in messages]
    if not dynamic_context:
        return request_messages
    for index in range(len(request_messages) - 1, -1, -1):
        if request_messages[index].get("role") == "user":
            return [
                *request_messages[:index],
                {"role": "system", "content": dynamic_context},
                *request_messages[index:],
            ]
    return [*request_messages, {"role": "system", "content": dynamic_context}]


@dataclass
class PromptContext:
    stable_prompt: str
    dynamic_context: str
    request_messages: list[dict[str, str]]
    brain_active: bool = False


class PromptContextAssembler:
    """Build memory, mood and tool context without mutating conversation state."""

    def __init__(
        self,
        *,
        memory_manager,
        mood_engine,
        topic_tracker,
        tool_registry,
        brain,
        config: dict,
    ) -> None:
        self._memory_manager = memory_manager
        self._mood_engine = mood_engine
        self._topic_tracker = topic_tracker
        self._tool_registry = tool_registry
        self._brain = brain
        self._config = config
        self.mcp_manager = None

    async def build(
        self,
        *,
        user_id: str,
        persona_id: str,
        persona,
        content: str,
        messages: list[dict[str, str]],
        relationship_level: int,
        message_count: int,
        thought: dict | None,
        retrieve_fallback: Callable[[str, str], Awaitable[list[str]]],
    ) -> PromptContext:
        memory_query = content
        if thought and thought.get("topic"):
            memory_query = f"{thought['topic']} {content}"
        memory_context = self._memory_manager.get_context_prompt(
            user_id, limit=8, query=memory_query,
        )
        relevant_context = ""
        if not memory_context:
            relevant = await retrieve_fallback(user_id, content)
            if relevant:
                relevant_context = "\n【与当前话题相关的记忆】\n" + "\n".join(
                    f"- {memory}" for memory in relevant
                )

        brain_enabled = self._config.get("brain_enabled", True)
        runtime_state = None
        if brain_enabled and self._brain:
            try:
                output = await self._brain.run(user_id, persona_id, user_message=content)
                runtime_state = getattr(output, "runtime_context", None)
                # Compatibility for third-party brain implementations that
                # predate the structured runtime context contract.
                if runtime_state is None:
                    runtime_state = getattr(output, "monologue", "")
            except Exception as e:
                logger.warning(f"BrainCoordinator failed: {e}, falling back to flat mode")
        brain_active = brain_enabled and bool(runtime_state)

        extra_parts = [f"当前时间：{get_time_context()}"]
        if thought and not brain_active:
            intent = thought.get("intent", "")
            if intent in ("撒娇", "抱怨", "倾诉", "表白"):
                extra_parts.append(f"对方似乎在{intent}，注意语气。")
        if brain_active:
            extra_parts.insert(0, runtime_state)
        elif self._mood_engine:
            mood_state = self._mood_engine.get_mood(user_id)
            style_hint = MoodExpressionEngine.get_style_instructions(mood_state)
            extra_parts.append(build_fused_style(persona, mood_state, style_hint))
        if message_count > 1:
            extra_parts.append(
                f"用户一口气发了 {message_count} 条消息。把它们当整体理解，自然地回应。"
            )

        tools_prompt = build_tools_prompt(self._tool_registry, self.mcp_manager)
        if tools_prompt:
            extra_parts.append(tools_prompt)
        if self._topic_tracker and not brain_active:
            topic_context = self._topic_tracker.get_topic_context()
            if topic_context:
                extra_parts.append(topic_context)

        stable_prompt = PromptBuilder.build_stable(persona)
        dynamic_context = PromptBuilder.build_dynamic_context(
            persona,
            memory_context=memory_context + relevant_context,
            extra_instructions="\n\n".join(filter(None, extra_parts)),
            relationship_level=relationship_level,
        )
        request_messages = insert_dynamic_context(messages, dynamic_context)
        context_budget = int(
            self._config.get("context_char_budget", DEFAULT_CONTEXT_CHAR_BUDGET)
        )
        request_messages = trim_messages_to_budget(
            request_messages,
            max_chars=max(4_000, context_budget),
            reserved_chars=len(stable_prompt),
        )
        return PromptContext(
            stable_prompt=stable_prompt,
            dynamic_context=dynamic_context,
            request_messages=request_messages,
            brain_active=brain_active,
        )
