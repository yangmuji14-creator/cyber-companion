"""记忆总结器 - 参考 My-Dream-Moments 的短期→长期记忆机制"""

from loguru import logger

from ..llm.base import BaseLLM


class MemorySummarizer:
    """记忆总结器

    机制（借鉴 My-Dream-Moments）：
    1. 短期记忆：保存最近的原始对话（用户+AI）
    2. 当短期记忆达到阈值（如 15 组对话），用 LLM 总结为长期记忆
    3. 长期记忆用于注入 prompt，短期记忆用于上下文连续性
    """

    def __init__(self, llm: BaseLLM, summarize_threshold: int = 15):
        self._llm = llm
        self._threshold = summarize_threshold

    async def summarize(self, conversations: list[dict[str, str]]) -> str | None:
        """将对话记录总结为长期记忆

        Args:
            conversations: 对话记录列表，格式 [{"user": "...", "assistant": "..."}]

        Returns:
            总结文本，失败返回 None
        """
        if len(conversations) < 3:
            return None

        # 构建对话文本
        lines = []
        for conv in conversations:
            lines.append(f"用户: {conv.get('user', '')}")
            lines.append(f"助手: {conv.get('assistant', '')}")
        conversation_text = "\n".join(lines)

        prompt = """请将以下对话记录总结为最重要的几条长期记忆。

要求：
1. 提取关键信息：人物、事件、地点、时间、偏好、情感
2. 每条记忆简洁明了，一句话概括
3. 按重要性排序
4. 忽略无意义的闲聊
5. 用中文简要表述

示例输出格式：
- 用户的生日是5月20日
- 用户喜欢吃火锅，不喜欢吃香菜
- 用户最近在准备考试，压力很大
- 用户养了一只猫叫小白"""

        try:
            response = await self._llm.chat(
                messages=[{"role": "user", "content": conversation_text}],
                system_prompt=prompt,
                max_tokens=500,
                temperature=0.3,
            )

            summary = response.content.strip()
            if summary and len(summary) > 10:
                logger.info(f"Memory summarized: {summary[:50]}...")
                return summary
            return None

        except Exception as e:
            logger.error(f"Memory summarization failed: {e}")
            return None

    async def extract_memory(self, user_msg: str, assistant_reply: str) -> dict | None:
        """从单条对话中提取记忆（LLM 辅助）

        Args:
            user_msg: 用户消息
            assistant_reply: AI 回复

        Returns:
            {"content": "提取的信息", "importance": 1-5} 或 None
        """
        prompt = f"""分析这段对话，判断是否包含值得长期记住的信息。

用户: {user_msg}
助手: {assistant_reply}

如果包含值得记住的信息（个人信息、偏好、重要事件、情感表达等），返回 JSON：
{{"content": "提取的信息", "importance": 1-5}}

重要度说明：
5 = 核心信息（生日、名字、关系里程碑）
4 = 重要事件（考试、旅行、纪念日）
3 = 个人偏好（喜欢/讨厌什么）
2 = 一般信息（日常安排、习惯）
1 = 不值得记住

如果没有值得记住的信息，返回：null"""

        try:
            response = await self._llm.chat(
                messages=[{"role": "user", "content": f"用户: {user_msg}\n助手: {assistant_reply}"}],
                system_prompt=prompt,
                max_tokens=200,
                temperature=0.1,
            )

            content = response.content.strip()

            # 解析响应
            if content.lower() == "null" or not content:
                return None

            # 尝试解析 JSON
            import json
            try:
                # 处理可能的 markdown 代码块
                if "```" in content:
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]
                result = json.loads(content.strip())
                if "content" in result and "importance" in result:
                    return result
            except json.JSONDecodeError:
                pass

            # JSON 解析失败，尝试从文本中提取
            if "content" in content and "importance" in content:
                # 简单提取
                lines = content.split("\n")
                for line in lines:
                    if "content" in line:
                        return {"content": line.split(":", 1)[1].strip().strip('",'), "importance": 3}

            return None

        except Exception as e:
            logger.error(f"Memory extraction failed: {e}")
            return None

    async def retrieve_relevant(self, query: str, memories: list[str], limit: int = 3) -> list[str]:
        """用 LLM 从记忆中检索相关条目（借鉴 My-Dream-Moments）

        Args:
            query: 用户当前消息
            memories: 长期记忆列表
            limit: 返回条数上限

        Returns:
            相关记忆列表
        """
        if not memories:
            return []

        memory_text = "\n".join(memories[-20:])  # 只取最近 20 条

        prompt = f"""请从以下记忆中找到与"{query}"最相关的条目，按相关性排序返回最多{limit}条。

记忆列表：
{memory_text}

要求：
1. 只返回相关性最高的条目
2. 保持原文不变，不要修改
3. 每条一行
4. 如果没有相关记忆，返回：无相关记忆"""

        try:
            response = await self._llm.chat(
                messages=[{"role": "user", "content": "请检索"}],
                system_prompt=prompt,
                max_tokens=300,
                temperature=0.1,
            )

            content = response.content.strip()
            if "无相关记忆" in content or not content:
                return []

            results = [line.strip() for line in content.split("\n") if line.strip() and line.strip() != "-"]
            return results[:limit]

        except Exception as e:
            logger.error(f"Memory retrieval failed: {e}")
            return []
