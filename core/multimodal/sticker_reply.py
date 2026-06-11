"""表情包回复系统

根据情感分析结果，从预设表情包/文字表情库中选择合适的表情回复。
纯文本实现（终端环境），支持 ASCII art 和颜文字。

策略：
- 高强度情感时自动附加表情包
- 根据关系等级选择不同风格的表情包
- 避免重复使用同一个表情
"""

import random
from collections import deque
from loguru import logger

from ..emotion.analyzer import EmotionType, EmotionResult


# 表情包库：按情感类型分类
STICKER_LIBRARY: dict[EmotionType, list[str]] = {
    EmotionType.HAPPY: [
        "(≧▽≦)",
        "(｡･ω･｡)",
        "ヾ(≧▽≦*)o",
        "(◕ᴗ◕✿)",
        "✧(≖ ◡ ≖✿)",
        "(◠‿◠)",
        "♪(´▽`)",
        "(☆▽☆)",
        "ヽ(✿ﾟ▽ﾟ)ノ",
        "(◡‿◡✿)",
    ],
    EmotionType.SAD: [
        "(´;ω;`)",
        "(;´д`)",
        "（；へ：）",
        "(T_T)",
        "(╯︵╰,)",
        "。･ﾟ･(つд`ﾟ)･ﾟ･。",
        "(｡•́︿•̀｡)",
        "(╥_╥)",
        "(つд⊂)",
        "orz",
    ],
    EmotionType.ANGRY: [
        "(╬▔皿▔)╯",
        "٩(╬ఠ༬ఠ)و",
        "(┛◉Д◉)┛彡┻━┻",
        "(╯°□°）╯︵ ┻━┻",
        "(`ε´)",
        "(≖_≖ )",
        "（♯｀∀´）",
        "凸(｀0´)凸",
    ],
    EmotionType.EXCITED: [
        "(*≧▽≦)",
        "✧(≖ ◡ ≖✿)",
        "(*°▽°*)",
        "＼(＾▽＾)／",
        "ヽ(>∀<☆)ノ",
        "(ﾉ◕ヮ◕)ﾉ*:・ﾟ✧",
        "☆*:.｡.o(≧▽≦)o.｡.:*☆",
        "(*≧∀≦*)",
    ],
    EmotionType.LONELY: [
        "(´･ω･`)",
        "（っ´Ι`）っ",
        "(｡•́︿•̀｡)",
        "(ノ_<。)",
        "(´• ω •`)",
        "（；´д｀）",
        "(｡T ω T｡)",
        "(つω`*)",
    ],
    EmotionType.ANXIOUS: [
        "(´;ω;`)",
        "orz",
        "(ﾉД`)",
        "（；´д｀）",
        "(;・∀・)",
        "(°ロ°) !",
        "(⊙_⊙)",
        "Σ(°△°|||)",
    ],
    EmotionType.LOVE: [
        "(♡˙︶˙♡)",
        "(◕‿◕✿)",
        "澪♡",
        "(´♡‿♡`)",
        "(◍•ᴗ•◍)❤",
        "(≧◡≦) ♡",
        "(｡♥‿♥｡)",
        "♡(ӦｖӦ｡)",
        "(⁄ ⁄•⁄ω⁄•⁄ ⁄)",
        "(*/ω＼*)",
    ],
    EmotionType.NEUTRAL: [
        "(・∀・)",
        "(￣▽￣)",
        "(─‿─)",
        "┐(´∀`)┌",
        "(・ω・)",
        "╮(─▽─)╭",
        "(．．)",
    ],
}

# 亲密关系专属表情（关系等级 >= 60 时可用）
INTIMATE_STICKERS = [
    "抱抱 (っ´Ι`)っ",
    "蹭蹭 (=^・ω・^=)",
    "亲亲 (*/ω＼*)",
    "想你了 (´♡‿♡`)",
    "mua~ (≧◡≦) ♡",
    "抱紧你 (っ˘̩╭╮˘̩)っ",
    "摸摸头 (｡･ω･｡)ﾉ♡",
]

# ASCII art 大表情（偶尔使用，增加趣味性）
ASCII_ARTS = {
    EmotionType.HAPPY: [
        """
  ∧＿∧
（｡･ω･｡)つ━☆・*。
⊂　　 ノ 　　　・゜+.
　しーＪ　　　°。+ *
""",
    ],
    EmotionType.LOVE: [
        """
　　 ♥♥♥♥♥♥
　 ♥♥♥♥♥♥♥♥
　♥♥♥♥♥♥♥♥♥♥
　 ♥♥♥♥♥♥♥♥♥
　　♥♥♥♥♥♥♥
　　　♥♥♥♥♥
　　　　♥♥♥
　　　　 ♥
""",
    ],
    EmotionType.SAD: [
        """
　∧＿∧
（；´д｀）
　（　　）
　　|　|　
""",
    ],
}


class StickerReplier:
    """表情包回复器

    根据情感分析结果选择合适的表情/颜文字。
    """

    def __init__(self, use_ascii_art: bool = False, ascii_art_chance: float = 0.05):
        self._use_ascii_art = use_ascii_art
        self._ascii_art_chance = ascii_art_chance
        self._recent_stickers: deque[str] = deque(maxlen=5)  # 避免重复

    def pick_sticker(
        self, emotion: EmotionResult, relationship_level: int = 50
    ) -> str | None:
        """根据情感和关系等级选择表情

        Args:
            emotion: 情感分析结果
            relationship_level: 关系亲密度 0-100

        Returns:
            表情字符串，不需要时返回 None
        """
        # 低强度情感不添加表情
        if emotion.intensity < 0.3:
            return None

        # 随机决定是否添加（避免每次都加）
        if random.random() > emotion.intensity:
            return None

        # 选择表情库
        stickers = STICKER_LIBRARY.get(emotion.emotion, STICKER_LIBRARY[EmotionType.NEUTRAL])

        # 亲密关系时混入专属表情
        if relationship_level >= 60 and emotion.emotion in (
            EmotionType.LOVE, EmotionType.HAPPY, EmotionType.NEUTRAL
        ):
            stickers = stickers + INTIMATE_STICKERS

        # 排除最近使用过的
        available = [s for s in stickers if s not in self._recent_stickers]
        if not available:
            available = stickers  # 全用过了就重置

        chosen = random.choice(available)
        self._recent_stickers.append(chosen)

        # 偶尔使用 ASCII art（如果启用）
        if self._use_ascii_art and random.random() < self._ascii_art_chance:
            arts = ASCII_ARTS.get(emotion.emotion)
            if arts:
                return random.choice(arts)

        return chosen

    def should_add_sticker(self, reply: str, emotion: EmotionResult) -> bool:
        """判断是否应该添加表情

        Args:
            reply: AI 回复文本
            emotion: 情感分析结果

        Returns:
            True 表示建议添加表情
        """
        # 回复中已经有很多 emoji 时不添加
        emoji_count = sum(1 for c in reply if ord(c) > 0x1F000)
        if emoji_count >= 3:
            return False

        # 回复太长时不添加（避免混乱）
        if len(reply) > 200:
            return False

        # 低强度不添加
        if emotion.intensity < 0.3:
            return False

        # 中性情感低概率添加
        if emotion.emotion == EmotionType.NEUTRAL:
            return random.random() < 0.1

        # 其他情况按强度概率添加
        return random.random() < emotion.intensity * 0.5

    def enhance_reply(
        self, reply: str, emotion: EmotionResult, relationship_level: int = 50
    ) -> str:
        """在回复中添加表情

        Args:
            reply: 原始回复
            emotion: 情感分析结果
            relationship_level: 关系亲密度

        Returns:
            增强后的回复
        """
        if not self.should_add_sticker(reply, emotion):
            return reply

        sticker = self.pick_sticker(emotion, relationship_level)
        if not sticker:
            return reply

        # 表情放在回复末尾或单独一行
        if len(reply) < 30:
            return f"{reply} {sticker}"
        else:
            return f"{reply}\n  {sticker}"