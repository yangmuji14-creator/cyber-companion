"""角色一致性保护器

生成回复后，检查 AI 回复是否符合角色设定。
如果检测到破防（跳出角色、语气不符等），自动重新生成。

策略：
- 用 LLM 做快速一致性检查（低温、短输出）
- 只在可疑情况下触发（长回复、高频率回复等）
- 检查失败时静默通过，不阻塞对话
"""

import json
from loguru import logger

from ..llm.base import BaseLLM


class ConsistencyGuard:
    """角色一致性保护器

    检查维度：
    1. 角色身份：AI 是否保持了角色身份（没有暴露自己是 AI）
    2. 语言风格：回复风格是否符合角色设定
    3. 情感一致：回复情感是否与角色情绪模式一致
    4. 知识边界：是否说了角色不应该知道的事情
    """

    CHECK_PROMPT = """你是一个角色扮演检查员。检查以下 AI 回复是否符合角色设定。

角色设定摘要：
{persona_summary}

AI 的回复：
{reply}

请检查以下维度，返回 JSON：
{{
    "consistent": true/false,
    "issues": ["问题1", "问题2"],
    "severity": "none/minor/major",
    "suggestion": "如何修正（仅在不一致时提供）"
}}

检查要点：
1. 身份一致性：是否保持了角色身份？有没有暴露自己是 AI/程序/模型？
2. 语言风格：回复是否自然口语化？有没有像机器人一样说话？
3. 角色设定：有没有说了不符合角色性格/年龄/背景的话？
4. 语言：是否始终使用中文？有没有突然切换成英文？

如果完全一致，consistent=true，issues=[]，severity="none"。
只返回 JSON，不要其他内容。"""

    # 破防关键词（快速检测，不需要 LLM）
    BREAK_KEYWORDS = [
        "作为一个人工智能", "作为AI", "作为语言模型", "作为助手",
        "我是AI", "我是人工智能", "我是语言模型", "我是助手",
        "我没有感情", "我没有情感", "我无法真正",
        "抱歉，我无法", "对不起，我不能",
        "I'm an AI", "As an AI", "I am an AI",
        "As a language model", "I don't have feelings",
    ]

    def __init__(self, llm: BaseLLM | None = None):
        self._llm = llm

    def set_llm(self, llm: BaseLLM) -> None:
        """延迟设置 LLM"""
        self._llm = llm

    def quick_check(self, reply: str) -> tuple[bool, str]:
        """快速关键词检测（零 LLM 成本）

        Args:
            reply: AI 回复内容

        Returns:
            (是否通过, 问题描述) 元组
        """
        reply_lower = reply.lower()
        for keyword in self.BREAK_KEYWORDS:
            if keyword.lower() in reply_lower:
                return False, f"检测到破防关键词：{keyword}"
        return True, ""

    async def deep_check(
        self, reply: str, persona_summary: str = ""
    ) -> dict | None:
        """深度一致性检查（LLM 辅助）

        仅在快速检查通过但回复可疑时触发。

        Args:
            reply: AI 回复内容
            persona_summary: 角色设定摘要

        Returns:
            检查结果 dict，失败返回 None
        """
        if not self._llm:
            return None

        # 只检查较长的回复（短回复一般没问题）
        if len(reply) < 20:
            return None

        prompt = self.CHECK_PROMPT.format(
            persona_summary=persona_summary or "（无角色设定摘要）",
            reply=reply,
        )

        try:
            response = await self._llm.chat(
                messages=[{"role": "user", "content": reply}],
                system_prompt=prompt,
                max_tokens=150,
                temperature=0.1,
            )

            result_text = response.content.strip()

            # 解析 JSON
            if "```" in result_text:
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]
                result_text = result_text.strip()

            result = json.loads(result_text)

            if not result.get("consistent", True):
                issues = result.get("issues", [])
                logger.warning(
                    f"Consistency check failed: {issues}"
                )

            return result

        except Exception as e:
            logger.debug(f"Consistency check failed: {e}")
            return None

    async def check_and_fix(
        self, reply: str, persona_summary: str = "",
        regenerate_fn=None, max_attempts: int = 1,
    ) -> str:
        """检查并修复不一致的回复

        Args:
            reply: AI 回复内容
            persona_summary: 角色设定摘要
            regenerate_fn: 重新生成回复的异步函数
            max_attempts: 最大重新生成次数

        Returns:
            修复后的回复（如果修复失败返回原始回复）
        """
        # 第一步：快速关键词检测
        passed, issue = self.quick_check(reply)
        if not passed:
            logger.warning(f"Quick check failed: {issue}")
            if regenerate_fn:
                for attempt in range(max_attempts):
                    try:
                        new_reply = await regenerate_fn()
                        if new_reply:
                            # 对新回复做快速检测
                            new_passed, _ = self.quick_check(new_reply)
                            if new_passed:
                                logger.info(
                                    f"Regenerated reply passed check "
                                    f"(attempt {attempt + 1})"
                                )
                                return new_reply
                    except Exception as e:
                        logger.debug(f"Regeneration failed: {e}")
            # 如果无法修复，返回原始回复
            return reply

        # 第二步：深度检查（仅对较长回复）
        if len(reply) > 50 and self._llm:
            check_result = await self.deep_check(reply, persona_summary)
            if check_result and not check_result.get("consistent", True):
                severity = check_result.get("severity", "none")
                if severity == "major" and regenerate_fn:
                    for attempt in range(max_attempts):
                        try:
                            new_reply = await regenerate_fn()
                            if new_reply:
                                new_passed, _ = self.quick_check(new_reply)
                                if new_passed:
                                    return new_reply
                        except Exception as e:
                            logger.debug(f"Regeneration failed: {e}")

        return reply