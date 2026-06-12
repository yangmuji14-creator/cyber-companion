"""LLM 情感分析器（升级版）

升级为默认分析器：
- 对所有消息用 LLM 分析（不再是 fallback）
- 支持上下文感知（带最近对话历史）
- 支持情感轨迹追踪
- 关键词分析作为快速 fallback（LLM 不可用时）

策略：关键词分析快速通过 + LLM 精确分析。
"""

import json
import re
from collections import deque
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


class EmotionTrajectory:
    """情感轨迹追踪器

    追踪最近 N 条消息的情绪变化趋势。
    """

    def __init__(self, window_size: int = 10):
        self._window_size = window_size
        self._history: deque[EmotionResult] = deque(maxlen=window_size)

    def add(self, emotion: EmotionResult) -> None:
        """添加一条情感记录"""
        self._history.append(emotion)

    def get_trend(self) -> str:
        """获取情感趋势

        Returns:
            "improving" = 情绪好转
            "declining" = 情绪恶化
            "stable" = 稳定
            "insufficient" = 数据不足
        """
        if len(self._history) < 3:
            return "insufficient"

        # 情感效价（正面=正数，负面=负数，中性=0）
        valence_map = {
            EmotionType.HAPPY: 1.0,
            EmotionType.EXCITED: 1.0,
            EmotionType.LOVE: 0.8,
            EmotionType.NEUTRAL: 0.0,
            EmotionType.LONELY: -0.5,
            EmotionType.ANXIOUS: -0.5,
            EmotionType.SAD: -1.0,
            EmotionType.ANGRY: -1.0,
        }

        recent = list(self._history)[-5:]  # 最近 5 条
        scores = [
            valence_map.get(e.emotion, 0) * e.intensity
            for e in recent
        ]

        if len(scores) < 3:
            return "stable"

        # 比较前半和后半
        mid = len(scores) // 2
        early_avg = sum(scores[:mid]) / max(mid, 1)
        late_avg = sum(scores[mid:]) / max(len(scores) - mid, 1)

        diff = late_avg - early_avg
        if diff > 0.3:
            return "improving"
        elif diff < -0.3:
            return "declining"
        else:
            return "stable"

    def get_dominant_emotion(self) -> EmotionType | None:
        """获取近期主导情感"""
        if not self._history:
            return None
        from collections import Counter
        emotions = Counter(e.emotion for e in self._history)
        return emotions.most_common(1)[0][0]

    def get_avg_intensity(self) -> float:
        """获取平均情感强度"""
        if not self._history:
            return 0.0
        return sum(e.intensity for e in self._history) / len(self._history)

    def is_persistent_negative(self) -> bool:
        """是否持续低落（最近 3+ 条都是负面情绪）"""
        if len(self._history) < 3:
            return False
        negative = {EmotionType.SAD, EmotionType.ANGRY, EmotionType.ANXIOUS, EmotionType.LONELY}
        recent = list(self._history)[-3:]
        return all(e.emotion in negative for e in recent)

    def clear(self) -> None:
        """清空轨迹"""
        self._history.clear()


class LLMEmotionAnalyzer:
    """LLM 情感分析器（升级版）

    策略：
    1. 对所有消息用 LLM 分析（带上下文）
    2. 如果 LLM 不可用，回退到关键词分析
    3. 追踪情感轨迹，提供趋势信息
    """

    ANALYZE_PROMPT = """分析以下文本的情感，返回 JSON 格式。

文本：{text}

最近对话上下文（用于理解语境）：
{context}

可选情感类型：{emotion_list}

返回格式：
{{"emotion": "情感类型", "intensity": 0.0-1.0, "reason": "简短原因"}}

注意：
- intensity 表示情感强度，0.0=完全中性，1.0=非常强烈
- 结合上下文判断，如"我没事"在难过话题后可能是"难过"
- 只返回 JSON，不要其他内容"""

    def __init__(self, llm: BaseLLM | None = None):
        self._llm = llm
        self._trajectory = EmotionTrajectory()

    def set_llm(self, llm: BaseLLM) -> None:
        """延迟设置 LLM（首次对话时初始化）"""
        self._llm = llm

    @property
    def trajectory(self) -> EmotionTrajectory:
        """获取情感轨迹"""
        return self._trajectory

    async def analyze(
        self, text: str, recent_messages: list[dict] | None = None
    ) -> EmotionResult:
        """分析文本情感（带上下文感知）

        Args:
            text: 要分析的文本
            recent_messages: 最近几条消息（用于上下文感知）

        Returns:
            EmotionResult 包含情感类型、强度和触发词
        """
        if not text:
            result = EmotionResult(EmotionType.NEUTRAL, 0.0, [])
            self._trajectory.add(result)
            return result

        result = None

        # 第一步：尝试 LLM 分析（带上下文）
        if self._llm:
            result = await self._llm_analyze_with_context(text, recent_messages)

        # 第二步：如果 LLM 失败，回退到关键词分析
        if result is None:
            result = EmotionAnalyzer.analyze(text)
            logger.debug(f"Using keyword emotion: {result.emotion.value}")

        # 记录到轨迹
        self._trajectory.add(result)
        return result

    async def _llm_analyze_with_context(
        self, text: str, recent_messages: list[dict] | None = None
    ) -> EmotionResult | None:
        """用 LLM 分析情感（带上下文）"""
        if not self._llm:
            return None

        # 构建上下文
        context = ""
        if recent_messages:
            recent = recent_messages[-6:]  # 最近 3 轮
            lines = []
            for msg in recent:
                role = "用户" if msg.get("role") == "user" else "助手"
                content = msg.get("content", "")[:80]
                lines.append(f"{role}: {content}")
            context = "\n".join(lines)
        else:
            context = "（无历史上下文）"

        emotion_list = "、".join(EMOTION_CN_MAP.values())

        prompt = self.ANALYZE_PROMPT.format(
            text=text,
            context=context,
            emotion_list=emotion_list,
        )

        try:
            response = await self._llm.chat(
                messages=[{"role": "user", "content": text}],
                system_prompt=prompt,
                max_tokens=150,
                temperature=0.1,
            )

            content = response.content.strip()

            # 解析 JSON（从 markdown 代码块中提取）
            code_block = re.search(r'```(?:json)?\s*\n(.*?)\n```', content, re.DOTALL)
            if code_block:
                content = code_block.group(1).strip()

            result = json.loads(content)

            emotion_cn = result.get("emotion", "中性")
            intensity = float(result.get("intensity", 0.5))
            reason = result.get("reason", "")

            emotion_type = CN_EMOTION_MAP.get(emotion_cn, EmotionType.NEUTRAL)
            intensity = max(0.0, min(1.0, intensity))

            logger.debug(
                f"LLM emotion: {emotion_type.value} ({intensity:.2f}), "
                f"reason={reason}"
            )

            return EmotionResult(
                emotion=emotion_type,
                intensity=round(intensity, 2),
                keywords=[f"LLM:{reason}"] if reason else [],
            )

        except Exception as e:
            logger.debug(f"LLM emotion analysis failed: {e}")
            return None