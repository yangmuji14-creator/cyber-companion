"""记忆重要度评分系统"""

import re
from loguru import logger


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
    def score(content: str) -> int:
        """评估一段内容的记忆重要度

        Args:
            content: 要评估的文本内容

        Returns:
            1-5 的重要度评分
        """
        if not content or len(content.strip()) < 3:
            return 1

        score = 1  # 基础分

        # 1. 关键词匹配加分
        for keyword, weight in KEYWORD_WEIGHTS.items():
            if keyword in content:
                score += weight

        # 2. 正则模式匹配加分
        for pattern in HIGH_IMPORTANCE_PATTERNS:
            if re.search(pattern, content):
                score += 2

        # 3. 长度加分（长文本通常包含更多信息）
        if len(content) > 50:
            score += 1
        if len(content) > 100:
            score += 1

        # 4. 包含数字加分（日期、电话等）
        if re.search(r"\d{2,}", content):
            score += 1

        # 限制在 1-5 范围
        final_score = min(max(score // 2, 1), 5)

        logger.debug(f"Memory score: {final_score} for '{content[:30]}...'")
        return final_score

    @staticmethod
    def should_remember(content: str, threshold: int = 2) -> bool:
        """判断是否值得记住"""
        return MemoryScorer.score(content) >= threshold
