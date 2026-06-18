"""CharacterBreakDetector — 人设一致性检查器

检测 AI 回复中的人设崩塌（character break）现象：
- 使用通用的 AI 语气（"作为AI"、"我是语言模型" 等）
- 切换到服务化语调（"有什么我可以帮你的"）
- 角色名与 AI 自我指代混用（"小雨" + "作为AI"）

纯规则驱动，不调用 LLM。
只检测不修改，不改变 reply 文本。

用法:
    detector = CharacterBreakDetector(persona_name="小雨")
    result = detector.check(reply, user_message)
    if result.is_break:
        print(f"触发词: {result.trigger_phrase}, 置信度: {result.confidence}")
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ────────── 通用 AI 语气模式（confidence=0.9）──────────
# 当 AI 直接暴露自己作为语言模型的本质时触发
_GENERIC_AI_PATTERNS: tuple[str, ...] = (
    "作为AI",
    "作为一个AI",
    "我是AI",
    "我是人工智能",
    "我没有情感",
    "作为语言模型",
    "作为大语言模型",
    "作为助手",
    "作为一个助手",
)

# ────────── 服务化语调模式（confidence=0.7）──────────
# 当 AI 切换到客服/助手式的服务用语时触发
_SERVICE_PATTERNS: tuple[str, ...] = (
    "有什么我可以帮你的",
    "我可以帮你",
    "请问你需要",
    "我能为你",
)

# ────────── 用户主动提及 AI 话题的触发词（不检测）──────────
# 当用户主动问 "你是不是AI" 等时，AI 回答 AI 相关内容是合理的
_USER_AI_MENTION_PATTERNS: tuple[str, ...] = (
    "你是不是AI",
    "你是机器人吗",
    "你是真人吗",
    "你是AI吗",
    "你到底是谁",
    "你是人工智能吗",
    "你是什么",
)


@dataclass
class CharacterBreakResult:
    """人设崩塌检测结果

    Attributes:
        is_break: 是否检测到人设崩塌
        trigger_phrase: 触发检测的具体短语（无崩塌时 None）
        confidence: 检测置信度 0.0-1.0（无崩塌时 0.0）
    """

    is_break: bool = False
    trigger_phrase: str | None = None
    confidence: float = 0.0


class CharacterBreakDetector:
    """人设一致性检查器

    检测 AI 回复中是否出现与当前人设不一致的通用 AI 语气。
    仅当 detector.enabled=True 时生效。

    Attributes:
        persona_name: 人设角色名（默认 "小雨"）
    """

    def __init__(self, persona_name: str = "小雨", enabled: bool = True):
        self._persona_name = persona_name
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value

    def check(self, reply: str, user_message: str = "") -> CharacterBreakResult:
        """检测回复中的人设崩塌

        Args:
            reply: AI 生成的回复文本
            user_message: 用户上一条消息（用于判断是否是用户先提 AI 话题）

        Returns:
            CharacterBreakResult: 检测结果
        """
        if not self._enabled or not reply:
            return CharacterBreakResult()

        # 上下文感知绕过：若用户主动提 AI 话题，即使回复含 AI 模式也不触发
        if user_message and self._user_mentioned_ai(user_message):
            return CharacterBreakResult()

        # 1. 通用 AI 语气检测（最高置信度）
        result = self._check_generic_ai_patterns(reply)
        if result.is_break:
            return result

        # 2. 服务化语调检测
        result = self._check_service_patterns(reply)
        if result.is_break:
            return result

        # 3. 角色名 + AI 自我指代混合检测
        result = self._check_character_name_switch(reply)
        if result.is_break:
            return result

        return CharacterBreakResult()

    # ────────── 内部检测方法 ──────────

    def _check_generic_ai_patterns(self, reply: str) -> CharacterBreakResult:
        """检测通用 AI 语气模式"""
        for pattern in _GENERIC_AI_PATTERNS:
            if pattern in reply:
                return CharacterBreakResult(
                    is_break=True,
                    trigger_phrase=pattern,
                    confidence=0.9,
                )
        return CharacterBreakResult()

    def _check_service_patterns(self, reply: str) -> CharacterBreakResult:
        """检测服务化语调模式"""
        for pattern in _SERVICE_PATTERNS:
            if pattern in reply:
                return CharacterBreakResult(
                    is_break=True,
                    trigger_phrase=pattern,
                    confidence=0.7,
                )
        return CharacterBreakResult()

    def _check_character_name_switch(self, reply: str) -> CharacterBreakResult:
        """检测角色名与 AI 自我指代混合

        当回复中同时出现角色名（如 "小雨"）和通用 AI 语气时，
        说明模型将角色与自身割裂看待，属于人设崩塌。
        """
        persona_name = self._persona_name
        if persona_name not in reply:
            return CharacterBreakResult()

        # 检查是否同时出现通用 AI 语气
        for pattern in _GENERIC_AI_PATTERNS:
            if pattern in reply:
                return CharacterBreakResult(
                    is_break=True,
                    trigger_phrase=f"{persona_name} + {pattern}",
                    confidence=0.9,
                )

        # 检查是否同时出现服务化语调
        for pattern in _SERVICE_PATTERNS:
            if pattern in reply:
                return CharacterBreakResult(
                    is_break=True,
                    trigger_phrase=f"{persona_name} + {pattern}",
                    confidence=0.7,
                )

        return CharacterBreakResult()

    # ────────── 上下文感知绕过 ──────────

    @staticmethod
    def _user_mentioned_ai(user_message: str) -> bool:
        """检查用户是否主动提到了 AI/机器人相关话题

        若用户主动问 AI 话题，AI 回复中提及自身是 AI 是合理的，
        不应视为人设崩塌。
        """
        for pattern in _USER_AI_MENTION_PATTERNS:
            if pattern in user_message:
                return True
        return False
