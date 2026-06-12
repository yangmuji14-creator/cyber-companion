"""Chain-of-Thought 对话思考器

在生成回复前，先内部推理用户意图、情绪状态、应该用什么语气，
将推理结果注入 system prompt，让 AI 回复更精准。

思考过程对用户不可见，只用于提升回复质量。
"""

import json
import re
from loguru import logger

from core.utils import parse_json_response
from ..llm.base import BaseLLM


class DialogueThinker:
    """对话思考器

    策略：
    - 简单消息（< 10 字、问候语等）跳过思考，零额外成本
    - 复杂消息（情感表达、提问、故事等）触发 CoT 思考
    - 思考结果作为 hidden instructions 注入 system prompt

    成本控制：
    - 用低温(0.1) + 短 max_tokens(200) 做思考，token 消耗约为回复的 1/5
    - 思考失败不阻塞对话，直接回退到无思考模式
    """

    THINK_PROMPT = """你是一个对话分析助手。分析用户的消息，输出你的推理过程。

用户消息：{user_message}

最近对话上下文：
{recent_context}

请用 JSON 格式输出你的分析：
{{
    "intent": "用户意图（提问/倾诉/分享/闲聊/求助/撒娇/抱怨/表白/其他）",
    "emotion_state": "用户情绪状态的简要描述",
    "topic": "当前话题关键词",
    "suggested_tone": "建议的回复语气（温柔/活泼/安慰/认真/俏皮/深情/日常）",
    "suggested_strategy": "建议的回复策略（1-2句话，如：先共情再给建议、顺着话题展开、用幽默化解尴尬等）",
    "key_points": ["需要回应的要点1", "要点2"]
}}

只返回 JSON，不要其他内容。"""

    # 跳过思考的消息模式（节省成本）
    SKIP_PATTERNS = {
        "嗯", "哦", "好的", "好吧", "哈哈", "嘻嘻", "嘿嘿",
        "hi", "hello", "嗨", "早", "晚安", "拜拜", "再见",
        "谢谢", "嗯嗯", "行", "ok", "好", "是的", "对",
    }

    def __init__(self, llm: BaseLLM | None = None):
        self._llm = llm

    def set_llm(self, llm: BaseLLM) -> None:
        """延迟设置 LLM"""
        self._llm = llm

    def _should_think(self, user_message: str) -> bool:
        """判断是否需要思考

        跳过条件：
        - 太短的消息（< 5 字）
        - 纯问候/应答
        - 纯 emoji
        """
        stripped = user_message.strip()

        # 太短
        if len(stripped) < 5:
            return False

        # 纯问候/应答
        if stripped.lower() in self.SKIP_PATTERNS:
            return False

        # 纯 emoji（没有中文/英文字符）
        if not re.search(r'[\u4e00-\u9fff\u0041-\u005a\u0061-\u007a]', stripped):
            return False

        return True

    async def think(
        self, user_message: str, recent_messages: list[dict] | None = None
    ) -> dict | None:
        """对话思考

        Args:
            user_message: 用户当前消息
            recent_messages: 最近几条消息（用于上下文理解）

        Returns:
            思考结果 dict，包含 intent/emotion_state/topic/suggested_tone 等
            跳过思考或失败时返回 None
        """
        if not self._llm:
            return None

        if not self._should_think(user_message):
            return None

        # 构建上下文
        context = ""
        if recent_messages:
            recent = recent_messages[-6:]  # 最近 3 轮
            lines = []
            for msg in recent:
                role = "用户" if msg.get("role") == "user" else "助手"
                content = msg.get("content", "")[:100]
                lines.append(f"{role}: {content}")
            context = "\n".join(lines)
        else:
            context = "（无历史上下文）"

        prompt = self.THINK_PROMPT.format(
            user_message=user_message,
            recent_context=context,
        )

        try:
            response = await self._llm.chat(
                messages=[{"role": "user", "content": user_message}],
                system_prompt=prompt,
                max_tokens=200,
                temperature=0.1,
            )

            result = parse_json_response(response.content)
            if not result:
                return None

            logger.debug(
                f"Thought: intent={result.get('intent')}, "
                f"tone={result.get('suggested_tone')}"
            )
            return result

        except Exception as e:
            logger.debug(f"Dialogue thinking failed: {e}")
            return None

    @staticmethod
    def format_thought_as_instruction(thought: dict) -> str:
        """将思考结果格式化为注入 system prompt 的指令

        Args:
            thought: think() 返回的结果

        Returns:
            格式化的指令文本
        """
        if not thought:
            return ""

        parts = []

        intent = thought.get("intent", "")
        if intent:
            parts.append(f"用户意图：{intent}")

        emotion = thought.get("emotion_state", "")
        if emotion:
            parts.append(f"用户情绪：{emotion}")

        tone = thought.get("suggested_tone", "")
        if tone:
            parts.append(f"建议语气：{tone}")

        strategy = thought.get("suggested_strategy", "")
        if strategy:
            parts.append(f"回复策略：{strategy}")

        key_points = thought.get("key_points", [])
        if key_points:
            points = "、".join(key_points)
            parts.append(f"需要回应的要点：{points}")

        if not parts:
            return ""

        return "【对话分析】\n" + "\n".join(parts)