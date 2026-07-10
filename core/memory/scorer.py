"""记忆重要度评分系统

双层评分策略：
1. 关键词 + 正则规则评分（快速、零成本）
2. LLM 智能评分（低置信度时启用，更准确）
"""

import re
from loguru import logger

from core.utils import parse_json_response


# 关键词权重表：关键词 -> 加分
KEYWORD_WEIGHTS: dict[str, int] = {
    # 个人信息（最高优先级）
    "生日": 3, "名字": 3, "年龄": 3, "地址": 3, "电话": 3, "学校": 3,
    "公司": 3, "工作": 2, "专业": 2, "家乡": 2,
    # 情感相关
    "喜欢": 2, "讨厌": 2, "爱": 2, "开心": 1, "难过": 1, "生气": 1,
    "害怕": 1, "梦想": 2, "希望": 1,
    # 重要事件
    "纪念日": 3, "结婚": 3, "毕业": 2, "旅行": 1, "第一次": 2,
    # 习惯偏好
    "习惯": 2, "最爱": 2, "最讨厌": 2, "经常": 1, "总是": 1,
    # 人物关系
    "家人": 2, "父母": 2, "朋友": 1, "同事": 1, "男朋友": 2, "女朋友": 2,
}

# 高重要度模式（正则）
HIGH_IMPORTANCE_PATTERNS = [
    r"我.{0,5}(?:叫|是)\s*\S+",           # 我叫xxx / 我是xxx
    r"(?:生日|出生).{0,10}\d",             # 生日相关 + 数字
    r"\d{1,2}月\d{1,2}[日号]",             # 日期
    r"(?:住在|家在|住在).{2,10}",          # 地址
    r"(?:最|特别|非常)(?:喜欢|讨厌|害怕)",  # 强烈情感
]

# 闲聊/寒暄模式（低重要度）
LOW_IMPORTANCE_PATTERNS = [
    r"^(?:嗯|哦|好的|好吧|哈哈|嘻嘻|嘿嘿|呵呵|hi|hello|嗨|早|晚安|拜拜|再见)$",
    r"^(?:是的|不是|对|对的|没错|嗯嗯|行|可以)$",
    r"^(?:谢谢|感谢|不客气|没事|没关系)$",
]


class MemoryScorer:
    """记忆重要度评分器

    评分规则：
    - Level 1: 闲聊、寒暄（不值得记住）
    - Level 2: 一般偏好、习惯
    - Level 3: 个人信息、情感表达
    - Level 4: 重要日期、关键事件
    - Level 5: 核心记忆（生日、名字、关系里程碑）
    """

    @staticmethod
    def score(content: str) -> tuple[int, float]:
        """评估一段内容的记忆重要度

        Args:
            content: 要评估的文本内容

        Returns:
            (评分 1-5, 置信度 0.0-1.0) 元组
            置信度 < 0.5 时建议用 LLM 二次评估
        """
        if not content or len(content.strip()) < 3:
            return 1, 0.9

        # 快速排除：闲聊模式
        stripped = content.strip()
        for pattern in LOW_IMPORTANCE_PATTERNS:
            if re.match(pattern, stripped, re.IGNORECASE):
                return 1, 0.9

        score = 1  # 基础分
        matched_signals = 0  # 匹配到的信号数量

        # 1. 关键词匹配加分
        for keyword, weight in KEYWORD_WEIGHTS.items():
            if keyword in content:
                score += weight
                matched_signals += 1

        # 2. 正则模式匹配加分
        for pattern in HIGH_IMPORTANCE_PATTERNS:
            if re.search(pattern, content):
                score += 2
                matched_signals += 1

        # 3. 长度加分（长文本通常包含更多信息）
        if len(content) > 50:
            score += 1
            matched_signals += 1
        if len(content) > 100:
            score += 1

        # 4. 包含数字加分（日期、电话等）
        if re.search(r"\d{2,}", content):
            score += 1
            matched_signals += 1

        # 限制在 1-5 范围
        final_score = min(max(score // 2, 1), 5)

        # 计算置信度：信号越多越确定
        # 0 信号 → 0.3（很可能是闲聊，但不确定）
        # 1 信号 → 0.5
        # 2+ 信号 → 0.7-0.9
        if matched_signals == 0:
            confidence = 0.3
        elif matched_signals == 1:
            confidence = 0.5
        elif matched_signals == 2:
            confidence = 0.7
        else:
            confidence = 0.9

        # 中等分数（2-3）且信号少时，置信度降低
        if 2 <= final_score <= 3 and matched_signals <= 1:
            confidence = min(confidence, 0.4)

        logger.debug(
            f"Memory score: {final_score} (confidence={confidence:.1f}) "
            f"signals={matched_signals} for '{content[:30]}...'"
        )
        return final_score, confidence

    @staticmethod
    def should_remember(content: str, threshold: int = 2) -> bool:
        """判断是否值得记住"""
        score, _ = MemoryScorer.score(content)
        return score >= threshold

    @staticmethod
    def needs_llm_evaluation(content: str) -> bool:
        """判断是否需要 LLM 辅助评分

        Args:
            content: 记忆内容

        Returns:
            True 表示建议用 LLM 二次评估
        """
        score, confidence = MemoryScorer.score(content)

        # 高分且高置信度 → 不需要 LLM
        if score >= 4 and confidence >= 0.7:
            return False

        # 低分且高置信度 → 不需要 LLM
        if score <= 1 and confidence >= 0.7:
            return False

        # 中等分数或低置信度 → 建议 LLM
        if confidence < 0.5:
            return True

        # 分数在边界值附近（2 分，刚好过/不过阈值）
        if score == 2:
            return True

        return False


class LLMMemoryScorer:
    """LLM 辅助记忆评分器

    当规则评分不确定时，用 LLM 进行更精确的评估。
    同时支持 LLM 辅助分类。
    """

    EVALUATE_PROMPT = """分析以下文本，判断它作为长期记忆的重要程度，并进行分类。

文本：{content}

请返回 JSON 格式：
{{
    "importance": 1-5,
    "category": "personal|emotion|event|preference|relationship|opinion|other",
    "reason": "简短原因"
}}

重要度标准：
1 = 闲聊寒暄，不值得记住（如：嗯、好的、哈哈）
2 = 一般信息，可记可不记（如：今天天气不错）
3 = 值得记住的偏好或情感（如：我喜欢吃火锅、今天心情不好）
4 = 重要个人信息或事件（如：我下周要考试、我养了一只猫叫小白）
5 = 核心信息（如：我叫xxx、我的生日是x月x日、我在xxx公司工作）

分类标准：
- personal：个人信息（姓名、生日、年龄、地址、工作等）
- emotion：情感表达（喜欢、讨厌、情绪感受）
- event：具体事件（旅行、考试、聚会等）
- preference：偏好习惯（饮食、音乐、运动等）
- relationship：人物关系（家人、朋友、恋人等）
- opinion：观点想法（对某事的看法）
- other：其他

只返回 JSON，不要其他内容。"""

    def __init__(self, llm=None):
        self._llm = llm

    async def evaluate(self, content: str) -> tuple[int, str] | None:
        """用 LLM 评估记忆重要度和分类

        Args:
            content: 记忆内容

        Returns:
            (importance, category) 元组，失败返回 None
        """
        if not self._llm:
            return None

        try:
            prompt = self.EVALUATE_PROMPT.format(content=content)
            response = await self._llm.chat(
                messages=[{"role": "user", "content": content}],
                system_prompt=prompt,
                max_tokens=150,
                temperature=0.1,
            )

            result = parse_json_response(response.content)
            if not result:
                logger.debug("LLM memory evaluation: failed to parse JSON response")
                return None

            importance = max(1, min(5, int(result.get("importance", 3))))
            category = result.get("category", "other")
            reason = result.get("reason", "")

            logger.info(
                f"LLM memory score: {importance}, category={category}, "
                f"reason={reason} for '{content[:30]}...'"
            )
            return importance, category

        except Exception as e:
            logger.debug(f"LLM memory evaluation failed: {e}")
            return None