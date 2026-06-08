"""情感表达 - 消息分段 + Emoji 增强"""

import re
import random
import asyncio
from dataclasses import dataclass

from .analyzer import EmotionType, EmotionResult


# 情感 → Emoji 映射表
EMOTION_EMOJI_MAP: dict[EmotionType, list[str]] = {
    EmotionType.HAPPY: ["😊", "😄", "🥰", "✨", "💕", "(≧▽≦)", "(｡･ω･｡)"],
    EmotionType.SAD: ["😢", "🥺", "💔", "😔", "(;´д`)", "(´;ω;`)"],
    EmotionType.ANGRY: ["😤", "💢", "(╬▔皿▔)╯", "٩(╬ఠ༬ఠ)و"],
    EmotionType.EXCITED: ["🎉", "🤩", "❗", "✨", "(*≧▽≦)", "✧(≖ ◡ ≖✿)"],
    EmotionType.LONELY: ["🥺", "😿", "💕", "(´･ω･`)", "（っ´Ι`）っ"],
    EmotionType.ANXIOUS: ["😰", "💪", "🫂", "(´;ω;`)", "orz"],
    EmotionType.LOVE: ["💖", "💗", "🥰", "😘", "💋", "(♡˙︶˙♡)", "澪♡"],
}


@dataclass
class SegmentedMessage:
    """分段后的消息"""
    segments: list[str]
    total_segments: int


class MessageSegmenter:
    """消息分段器

    借鉴 My-Dream-Moments 的消息分段逻辑：
    - 按句号、感叹号、问号、省略号、换行符断句
    - 过长段落（>50字）强制在标点处断开
    - 每段之间加随机延迟模拟真人打字
    """

    # 断句标点
    SPLIT_PATTERN = r'(?<=[。！？…\n])'

    @staticmethod
    def segment(text: str, max_segment_length: int = 50) -> SegmentedMessage:
        """将长消息分段

        Args:
            text: 原始消息
            max_segment_length: 单段最大长度

        Returns:
            SegmentedMessage 包含分段列表
        """
        if not text or len(text) <= max_segment_length:
            return SegmentedMessage(segments=[text], total_segments=1)

        # 第一步：按自然断句分割
        raw_segments = re.split(MessageSegmenter.SPLIT_PATTERN, text)
        raw_segments = [s.strip() for s in raw_segments if s.strip()]

        # 第二步：合并过短的段落，拆分过长的段落
        final_segments = []
        buffer = ""

        for seg in raw_segments:
            # 如果 buffer + 当前段落不超限，合并
            if buffer and len(buffer) + len(seg) <= max_segment_length:
                buffer += seg
            elif buffer:
                final_segments.append(buffer)
                buffer = seg
            else:
                # 单段太长，强制拆分
                if len(seg) > max_segment_length:
                    chunks = MessageSegmenter._force_split(seg, max_segment_length)
                    final_segments.extend(chunks)
                    buffer = ""
                else:
                    buffer = seg

        if buffer:
            final_segments.append(buffer)

        return SegmentedMessage(
            segments=final_segments,
            total_segments=len(final_segments),
        )

    @staticmethod
    def _force_split(text: str, max_length: int) -> list[str]:
        """强制拆分过长段落"""
        chunks = []
        while len(text) > max_length:
            # 在 max_length 附近找标点断点
            cut_pos = max_length
            for i in range(min(max_length, len(text) - 1), max(0, max_length - 20), -1):
                if text[i] in "，、；：,;:":
                    cut_pos = i + 1
                    break
            chunks.append(text[:cut_pos].strip())
            text = text[cut_pos:].strip()
        if text:
            chunks.append(text)
        return chunks


class EmotionEnhancer:
    """情感增强器 - 根据情感分析结果增强回复"""

    @staticmethod
    def enhance_reply(reply: str, emotion: EmotionResult) -> str:
        """根据情感在回复中添加 emoji

        Args:
            reply: 原始回复
            emotion: 情感分析结果

        Returns:
            增强后的回复
        """
        if emotion.emotion == EmotionType.NEUTRAL:
            return reply

        emojis = EMOTION_EMOJI_MAP.get(emotion.emotion, [])
        if not emojis:
            return reply

        # 如果回复中已经包含类似 emoji，不重复添加
        if any(e in reply for e in emojis):
            return reply

        # 根据强度决定是否添加
        if emotion.intensity < 0.3:
            return reply

        # 随机选择一个 emoji 添加到末尾
        chosen = random.choice(emojis)
        return f"{reply} {chosen}"

    @staticmethod
    def get_typing_delay(segment_index: int, total_segments: int) -> float:
        """获取模拟打字延迟（秒）

        第一段延迟稍长（模拟思考），中间段短，最后一段不延迟
        """
        if segment_index == 0:
            return random.uniform(1.5, 3.0)
        elif segment_index >= total_segments - 1:
            return 0
        else:
            # 根据段落长度调整延迟
            return random.uniform(1.0, 2.5)
