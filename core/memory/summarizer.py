"""记忆总结器 + 智能检索

机制：
1. 短期记忆：保存最近的原始对话（用户+AI）
2. 当短期记忆达到阈值，用 LLM 总结为长期记忆
3. 检索：多路召回（关键词 + 标签 + 分类） + LLM 重排序
"""

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
            {"content": "提取的信息", "importance": 1-5, "category": "..."} 或 None
        """
        prompt = f"""分析这段对话，判断是否包含值得长期记住的信息。

用户: {user_msg}
助手: {assistant_reply}

如果包含值得记住的信息（个人信息、偏好、重要事件、情感表达等），返回 JSON：
{{"content": "提取的信息", "importance": 1-5, "category": "personal|emotion|event|preference|relationship|opinion|other"}}

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

    async def retrieve_relevant(
        self, query: str, memories: list, limit: int = 5
    ) -> list[str]:
        """智能检索相关记忆：多路召回 + LLM 重排序

        Args:
            query: 用户当前消息
            memories: 记忆对象列表（Memory 实例或 content 字符串）
            limit: 返回条数上限

        Returns:
            相关记忆内容列表
        """
        if not memories:
            return []

        # 处理输入：兼容 Memory 对象和字符串
        if hasattr(memories[0], 'content'):
            # Memory 对象
            memory_items = [
                {
                    "content": m.content,
                    "category": getattr(m, 'category', 'other'),
                    "level": getattr(m, 'level', 1),
                    "access_count": getattr(m, 'access_count', 0),
                }
                for m in memories
            ]
        else:
            # 纯字符串列表（兼容旧接口）
            memory_items = [
                {"content": m, "category": "other", "level": 1, "access_count": 0}
                for m in memories
            ]

        # === 第一阶段：多路召回 ===
        recalled = self._multi_path_recall(query, memory_items, recall_limit=15)

        if not recalled:
            return []

        if len(recalled) <= limit:
            return [item["content"] for item in recalled]

        # === 第二阶段：LLM 重排序 ===
        if self._llm:
            try:
                ranked = await self._llm_rerank(query, recalled, limit)
                if ranked:
                    return ranked
            except Exception as e:
                logger.debug(f"LLM rerank failed, falling back to rule-based: {e}")

        # 回退：按 level 降序取前 N
        recalled.sort(key=lambda x: x.get("level", 1), reverse=True)
        return [item["content"] for item in recalled[:limit]]

    def _multi_path_recall(
        self, query: str, memory_items: list[dict], recall_limit: int = 15
    ) -> list[dict]:
        """多路召回：关键词 + 分类 + 热度

        Args:
            query: 查询文本
            memory_items: 记忆条目列表
            recall_limit: 召回数量上限

        Returns:
            召回的记忆条目（可能有重复，需去重）
        """
        seen_ids: set[str] = set()
        recalled: list[dict] = []

        def _add(item: dict, match_type: str):
            content = item["content"]
            if content not in seen_ids:
                seen_ids.add(content)
                item_copy = dict(item)
                item_copy["match_type"] = match_type
                recalled.append(item_copy)

        # 1. 关键词召回：query 中的词出现在记忆中
        query_chars = set(query.replace(" ", "").replace("？", "").replace("。", ""))
        for item in memory_items:
            content = item["content"]
            content_chars = set(content)
            overlap = len(query_chars & content_chars)
            if overlap >= 2:  # 至少 2 个字符匹配
                _add(item, "keyword")

        # 2. 分类召回：根据 query 意图匹配分类
        category_hints = {
            "personal": ["叫什么", "名字", "生日", "多大", "住哪", "在哪"],
            "emotion": ["开心", "难过", "喜欢", "讨厌", "心情", "感觉"],
            "event": ["什么时候", "去了", "做了", "发生", "经历"],
            "preference": ["喜欢什么", "爱吃什么", "习惯", "爱好"],
            "relationship": ["家人", "朋友", "爸妈", "男朋友", "女朋友"],
        }
        for category, hints in category_hints.items():
            if any(hint in query for hint in hints):
                for item in memory_items:
                    if item.get("category") == category:
                        _add(item, "category")

        # 3. 热度召回：高访问次数 + 高重要度的记忆始终可召回
        for item in memory_items:
            if item.get("level", 1) >= 4 or item.get("access_count", 0) >= 3:
                _add(item, "hot")

        # 限制召回数量
        return recalled[:recall_limit]

    async def _llm_rerank(
        self, query: str, candidates: list[dict], limit: int
    ) -> list[str] | None:
        """LLM 重排序：从候选中选出最相关的

        Args:
            query: 查询文本
            candidates: 候选记忆条目
            limit: 返回数量

        Returns:
            重排序后的记忆内容列表
        """
        # 构建候选列表文本
        candidate_lines = []
        for i, item in enumerate(candidates):
            candidate_lines.append(f"{i + 1}. {item['content']}")
        candidate_text = "\n".join(candidate_lines)

        prompt = f"""从以下记忆中选出与用户问题最相关的条目。

用户问题：{query}

记忆列表：
{candidate_text}

要求：
1. 只返回最相关的 {limit} 条记忆的编号（如：1,3,5）
2. 按相关性从高到低排序
3. 如果都不相关，返回：无
4. 只返回编号，不要其他内容"""

        try:
            response = await self._llm.chat(
                messages=[{"role": "user", "content": "请排序"}],
                system_prompt=prompt,
                max_tokens=100,
                temperature=0.1,
            )

            content = response.content.strip()

            if "无" in content and len(content) < 5:
                return []

            # 解析编号
            import re
            numbers = re.findall(r'\d+', content)
            if not numbers:
                return None

            results = []
            for num_str in numbers:
                idx = int(num_str) - 1
                if 0 <= idx < len(candidates):
                    results.append(candidates[idx]["content"])
                    if len(results) >= limit:
                        break

            return results if results else None

        except Exception as e:
            logger.debug(f"LLM rerank error: {e}")
            return None