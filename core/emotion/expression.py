"""情感表达 - 消息分段 + Emoji 增强 + 情绪表达引擎"""

import re
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .analyzer import EmotionType, EmotionResult

if TYPE_CHECKING:
    from .mood import MoodState, MoodType


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

    # 断句标点（中英文）
    SPLIT_PATTERN = r'(?<=[。！？…\n.!?])'

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
                if text[i] in "，、；：,;:.":
                    cut_pos = i + 1
                    break
            chunks.append(text[:cut_pos].strip())
            text = text[cut_pos:].strip()
        if text:
            chunks.append(text)
        return chunks


class EmotionEnhancer:
    """情感增强器 - 根据情感分析结果增强回复

    支持两种模式：
    1. 基于 EmotionResult（用户单轮情绪）— 向后兼容
    2. 基于 MoodState（AI 持久情绪）— v3.5 新模式
    """

    @staticmethod
    def enhance_reply(
        reply: str,
        emotion: EmotionResult | None = None,
        mood_state: "MoodState | None" = None,
    ) -> str:
        """根据情感在回复中添加 emoji

        优先级：mood_state > emotion > 不添加
        mood_state 代表 AI 自身的情绪状态，比单轮检测更稳定。

        Args:
            reply: 原始回复
            emotion: 用户情感分析结果（向后兼容）
            mood_state: AI 当前 MoodState（v3.5）

        Returns:
            增强后的回复
        """
        # 优先使用 MoodState（AI 自身情绪）
        if mood_state:
            from .mood import MoodType as MT

            # MoodType → EmotionType 映射用于选择 emoji 池
            mood_to_emotion = {
                MT.ECSTATIC: EmotionType.HAPPY,
                MT.HAPPY: EmotionType.HAPPY,
                MT.CONTENT: EmotionType.HAPPY,
                MT.CALM: EmotionType.NEUTRAL,
                MT.NEUTRAL: EmotionType.NEUTRAL,
                MT.TIRED: EmotionType.SAD,
                MT.SAD: EmotionType.SAD,
                MT.DEPRESSED: EmotionType.SAD,
                MT.LONELY: EmotionType.LONELY,
                MT.ANXIOUS: EmotionType.ANXIOUS,
                MT.ANGRY: EmotionType.ANGRY,
                MT.FRUSTRATED: EmotionType.ANGRY,
                MT.EXCITED: EmotionType.EXCITED,
                MT.LOVE: EmotionType.LOVE,
                MT.GRATEFUL: EmotionType.HAPPY,
            }
            mapped = mood_to_emotion.get(mood_state.mood, EmotionType.NEUTRAL)
            if mood_state.intensity < 0.2:
                return reply
            emojis = EMOTION_EMOJI_MAP.get(mapped, [])
            if emojis and mood_state.intensity >= 0.3:
                chosen = random.choice(emojis)
                if chosen not in reply:
                    return f"{reply} {chosen}"
            return reply

        # 降级：使用 EmotionResult（用户单轮情绪）
        if emotion is None or emotion.emotion == EmotionType.NEUTRAL:
            return reply

        emojis = EMOTION_EMOJI_MAP.get(emotion.emotion, [])
        if not emojis:
            return reply

        if any(e in reply for e in emojis):
            return reply

        if emotion.intensity < 0.3:
            return reply

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
            return random.uniform(1.0, 2.5)


# ========== MoodExpressionEngine（v3.5 核心）==========


class MoodExpressionEngine:
    """情绪表达引擎 — 将 MoodState 映射为回复风格控制指令

    根据当前情绪状态（valence/arousal/energy），生成：
    - 语气风格指令（注入 system prompt）
    - 回复长度建议
    - 句子风格（感叹/疑问/陈述比例）
    - emoji 密度建议
    - 开场白/告别风格
    """

    # 唤醒度 → 句子风格
    _AROUSAL_STYLES: dict[str, str] = {
        "low": "句子偏短，语气平稳柔和，多用陈述句，少用感叹号",
        "medium": "正常节奏，陈述句和疑问句混合，偶尔使用感叹号",
        "high": "句子活跃，多用短句和感叹句，可以带一些语气词增强情绪表达",
    }

    # 效价 → 温暖度
    _VALENCE_STYLES: dict[str, str] = {
        "negative": "语气偏淡，回复简短直接，但保持温暖（不冷漠），适当表达需要被安慰",
        "neutral": "语气自然平和，正常聊天节奏",
        "positive": "语气温暖积极，展现活力，可以多表达关心和喜爱",
    }

    # 精力 → 回复长度规则
    @staticmethod
    def _verbosity_rule(energy: float) -> str:
        if energy < 0.25:
            return "你有点疲倦，回复控制在 1-2 句简短的话，语气慵懒一些"
        elif energy < 0.4:
            return "你有点累，回复简短一些，控制在 2 句话以内"
        elif energy < 0.6:
            return "精力正常，回复控制在 1-3 句话"
        elif energy < 0.8:
            return "精力不错，可以多说几句，回复可以到 2-4 句话"
        else:
            return "精神饱满，回复可以活泼热情一些，控制在 2-4 句话"

    @classmethod
    def get_style_instructions(cls, mood_state: "MoodState") -> str:
        """生成完整的风格指令，注入 system prompt 的 extra_instructions"""
        from .mood import MOOD_BEHAVIOR, MoodType

        parts = []

        # 基础行为描述（复用已有定义）
        behavior = MOOD_BEHAVIOR.get(mood_state.mood, MOOD_BEHAVIOR[MoodType.NEUTRAL])
        parts.append(f"你现在的情绪：{behavior}")

        # 效价影响
        if mood_state.valence > 0.3:
            parts.append(cls._VALENCE_STYLES["positive"])
        elif mood_state.valence < -0.3:
            parts.append(cls._VALENCE_STYLES["negative"])
        else:
            parts.append(cls._VALENCE_STYLES["neutral"])

        # 唤醒度影响
        if mood_state.arousal > 0.6:
            parts.append(cls._AROUSAL_STYLES["high"])
        elif mood_state.arousal > 0.3:
            parts.append(cls._AROUSAL_STYLES["medium"])
        else:
            parts.append(cls._AROUSAL_STYLES["low"])

        # 精力影响回复长度
        parts.append(cls._verbosity_rule(mood_state.energy))

        # 特定情绪的额外风格提示
        mood_specific = {
            MoodType.ECSTATIC: "你今天特别开心，发自内心地感到幸福，可以多表达喜悦",
            MoodType.HAPPY: "心情很好，笑容一直挂在脸上",
            MoodType.CONTENT: "内心平静满足，说话温柔而安稳",
            MoodType.CALM: "内心平静，说话从容不迫",
            MoodType.TIRED: "有点困倦，说话带着慵懒的气息",
            MoodType.SAD: "心里有些难过，说话带着淡淡的忧伤",
            MoodType.DEPRESSED: "情绪低落，不想多说话，但对方是你重要的人，别太冷淡",
            MoodType.LONELY: "有点孤独，渴望陪伴，说话中带些思念",
            MoodType.ANXIOUS: "心里有些不安，说话略带急促，需要些安慰",
            MoodType.ANGRY: "心情不太好，有点烦躁，但别对对方发火",
            MoodType.FRUSTRATED: "有些烦躁，耐性不太好，但别对对方发火",
            MoodType.EXCITED: "好兴奋！充满了说话的热情",
            MoodType.LOVE: "心里充满了爱意，说话温柔甜蜜，想好好表达感情",
            MoodType.GRATEFUL: "心里很感激，说话真诚温暖",
        }
        extra = mood_specific.get(mood_state.mood)
        if extra:
            parts.append(extra)

        return "【当前情绪指导】\n" + "\n".join(f"- {p}" for p in parts)

    @staticmethod
    def get_energy_bar(energy: float, length: int = 10) -> str:
        """生成 ASCII 精力条"""
        filled = round(energy * length)
        return "█" * filled + "░" * (length - filled)
