"""人设一致性检查器

检测 AI 回复内容是否与人设配置冲突。
例如：人设设定「讨厌香菜」，回复却说「我最喜欢香菜」——判定为冲突。

检测维度：
1. 偏好冲突：回复中提到的偏好与人设设定的喜好相反
2. 身份冲突：回复中提到的个人特征与人设描述不符
3. 行为冲突：回复中的行为描述与人设的行为倾向相反
"""

import re
from dataclasses import dataclass, field
from typing import Any

from loguru import logger
from core.config import DEFAULT_PERSONA_ID


@dataclass
class ConsistencyCheckResult:
    """一致性检查结果"""
    passed: bool
    issues: list[str] = field(default_factory=list)
    severity: str = "none"  # none / minor / major


class PersonaConsistencyChecker:
    """人设一致性检查器

    不需要 LLM 调用，基于关键词和规则匹配。
    快速的静态分析，适合每次回复后调用。
    """

    # 强烈偏好词（正）
    STRONG_LIKE_WORDS = {"喜欢", "爱", "最爱", "超喜欢", "特别喜欢", "好喜欢"}
    # 强烈厌恶词（负）
    STRONG_DISLIKE_WORDS = {"讨厌", "恨", "最讨厌", "特别讨厌", "受不了", "吃不下", "恶心"}

    def __init__(self, persona_loader=None, persona=None):
        """
        Args:
            persona_loader: PersonaLoader 实例，用于获取人设数据
            persona: 直接传入的人设对象（用于测试或绕开 loader）
        """
        self._persona_loader = persona_loader
        self._persona = persona

    def check_reply(self, reply: str, persona_id: str = DEFAULT_PERSONA_ID) -> ConsistencyCheckResult:
        """检查回复是否与人设冲突

        Args:
            reply: AI 生成的回复文本
            persona_id: 人设 ID（仅当未通过 __init__ 传入 persona 时使用）

        Returns:
            检查结果
        """
        result = ConsistencyCheckResult(passed=True)

        # 优先使用传入的 persona 对象，其次是 loader 获取
        persona = self._persona
        if persona is None and self._persona_loader:
            persona = self._persona_loader.get(persona_id)

        if persona is None:
            return result

        # 1. 检查偏好冲突（人设讨厌的 vs 回复说喜欢）
        taboos = getattr(persona, 'taboos', []) or []
        for taboo in taboos:
            if self._detect_preference_conflict(reply, taboo):
                result.issues.append(
                    f"偏好冲突：人设讨厌「{taboo}」，但回复提及正面态度"
                )
                result.severity = "major"

        # 2. 检查性格冲突（行为规则违反）
        behavior_rules = getattr(persona, 'behavior_rules', []) or []
        for rule in behavior_rules:
            if self._detect_behavior_conflict(reply, rule):
                result.issues.append(
                    f"行为冲突：人设规则「{rule}」，但回复内容矛盾"
                )
                if result.severity == "none":
                    result.severity = "minor"

        # 3. 检查语言风格冲突（人设用语 vs 回复用语）
        speaking_style = getattr(persona, 'speaking_style', '') or ''
        if speaking_style:
            if self._detect_style_conflict(reply, speaking_style):
                result.issues.append(
                    f"风格冲突：人设说话风格「{speaking_style}」，但回复不符合"
                )
                if result.severity == "none":
                    result.severity = "minor"

        # 更新结果
        result.passed = len(result.issues) == 0
        if result.issues:
            logger.warning(
                f"Persona consistency check failed for {persona_id}: {result.issues}"
            )
        return result

    @staticmethod
    def _detect_preference_conflict(reply: str, taboo: str) -> bool:
        """检测偏好冲突：回复中对禁忌内容表达了正面态度"""
        if taboo not in reply:
            return False

        # 检查禁忌内容附近是否有正面词汇
        idx = reply.find(taboo)
        start = max(0, idx - 20)
        end = min(len(reply), idx + len(taboo) + 30)
        context = reply[start:end]

        # 检查正面词汇
        for word in PersonaConsistencyChecker.STRONG_LIKE_WORDS:
            if word in context:
                return True

        return False

    @staticmethod
    def _detect_behavior_conflict(reply: str, rule: str) -> bool:
        """检测行为冲突：回复违反了行为规则

        规则格式如"不要主动提及某话题"、"不可以怎样"
        """
        # 提取规则中的否定关键词
        neg_patterns = re.findall(r'(不要|不可以|不能|别|禁止)(.{2,10})', rule)
        for neg_word, target in neg_patterns:
            if target.strip() in reply:
                # 确认回复中确实做了规则禁止的事
                return True
        return False

    @staticmethod
    def _detect_style_conflict(reply: str, style: str) -> bool:
        """检测风格冲突：回复风格与人设设定不符"""
        # 如果人设是"高冷话少"，回复太长则冲突
        if "话少" in style or "高冷" in style or "冷淡" in style:
            if len(reply) > 150:
                return True

        # 如果人设是"活泼话多"，回复太短则冲突
        if "话多" in style or "活泼" in style or "热情" in style:
            if len(reply) < 10:
                return True

        # 如果人设说"用敬语"，检查是否包含敬语
        if "敬语" in style or "礼貌" in style:
            honorifics = {"您", "请问", "谢谢", "不好意思", "抱歉"}
            if not any(h in reply for h in honorifics) and len(reply) > 20:
                return True

        return False
