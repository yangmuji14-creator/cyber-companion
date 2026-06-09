"""LLM 辅助情感分析器

当关键词匹配不确定时，用 LLM 进行更精确的情感判断。
"""

import json
from loguru import logger

from .analyzer import EmotionAnalyzer, EmotionType, EmotionResult
from ..llm.base import BaseLLM


# 情感类型中文映射
EMOTION_CN_MAP = {
    EmotionType.HAPPY: "开心",
    EmotionType.SAD: "难过",
    EmotionType.ANGRY: "生气",
    EmotionType.NEUTRAL: "中性",
    EmotionType.EXCITED: "兴奋",
    EmotionType.LONELY: "孤独",
    EmotionType.ANXIOUS: "焦虑",
    EmotionType.LOVE: "爱意",
}

# 中文 → 情感类型反向映射
CN_EMOTION_MAP = {v: k for k, v in EMOTION_CN_MAP.items()}


class LLMEmotionAnalyzer:
    """LLM 辅助情感分析器

    策略：
    1. 先用关键词分析（快速、零成本）
    2. 如果结果是 NEUTRAL 或强度很低，用 LLM 做二次判断
    3. LLM 结果作为最终结果

    这样大部分简单消息走关键词（零成本），复杂消息走 LLM（更准确）。
    """

    # 关键词分析置信度阈值：低于此值时启用 LLM
    CONFIDENCE_THRESHOLD = 0.3

    def __init__(self, llm: BaseLLM | None = None):
        self._llm = llm

    async def analyze(self, text: str) -> EmotionResult:
        """分析文本情感

        Args:
            text: 要分析的文本

        Returns:
            EmotionResult 包含情感类型、强度和触发词
        """
        if not text:
            return EmotionResult(EmotionType.NEUTRAL, 0.0, [])

        # 第一步：关键词分析
        keyword_result = EmotionAnalyzer.analyze(text)

        # 第二步：判断是否需要 LLM 辅助
        if self._llm and self._should_use_llm(text, keyword_result):
            llm_result = await self._llm_analyze(text)
            if llm_result:
                logger.debug(f"LLM emotion override: {keyword_result.emotion.value} → {llm_result.emotion.value}")
                return llm_result

        return keyword_result

    def _should_use_llm(self, text: str, result: EmotionResult) -> bool:
        """判断是否需要 LLM 辅助

        触发条件：
        1. 关键词分析结果是 NEUTRAL（可能有复杂情感）
        2. 强度很低（匹配不明确）
        3. 文本较长（可能包含复杂表达）
        """
        if result.emotion == EmotionType.NEUTRAL and len(text) > 5:
            return True
        if result.intensity < self.CONFIDENCE_THRESHOLD and len(text) > 10:
            return True
        return False

    async def _llm_analyze(self, text: str) -> EmotionResult | None:
        """用 LLM 分析情感"""
        emotion_list = "、".join(EMOTION_CN_MAP.values())

        prompt = f"""分析以下文本的情感，返回 JSON 格式。

文本：{text}

可选情感类型：{emotion_list}

返回格式：
{{"emotion": "情感类型", "intensity": 0.0-1.0, "reason": "简短原因"}}

注意：
- intensity 表示情感强度，0.0=完全中性，1.0=非常强烈
- 只返回 JSON，不要其他内容"""

        try:
            response = await self._llm.chat(
                messages=[{"role": "user", "content": text}],
                system_prompt=prompt,
                max_tokens=150,
                temperature=0.1,
            )

            content = response.content.strip()

            # 解析 JSON
            if "```" in content:
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()

            result = json.loads(content)

            emotion_cn = result.get("emotion", "中性")
            intensity = float(result.get("intensity", 0.5))

            emotion_type = CN_EMOTION_MAP.get(emotion_cn, EmotionType.NEUTRAL)
            intensity = max(0.0, min(1.0, intensity))

            return EmotionResult(
                emotion=emotion_type,
                intensity=round(intensity, 2),
                keywords=[f"LLM:{result.get('reason', '')}"],
            )

        except Exception as e:
            logger.debug(f"LLM emotion analysis failed: {e}")
            return None
