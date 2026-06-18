"""LLM 输出解析测试 — 亲密度/情感解析器

预期失败（RED）：
这些测试定义了亲和力/情感 LLM 输出解析的期望行为，
但解析器尚未实现（将在 Task 11 添加到 LLMEmotionAnalyzer）。
"""

import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest

from core.emotion.llm_analyzer import LLMEmotionAnalyzer
from core.emotion.analyzer import EmotionType, EmotionResult
from core.social.affection.constants import AffectionDirection, AffectionLevel


# ═══════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════

def _make_valid_llm_json() -> dict:
    """返回完整的有效 LLM JSON 作为解析输入"""
    return {
        "emotion_understanding": "User seems happy",
        "emotional_needs": ["被理解"],
        "affection_impact": {
            "direction": "positive",
            "level": "high",
            "reason": "good vibes",
        },
        "personality_shift": {
            "trust": "up",
            "dependence": "no_change",
        },
        "response_guidance": {
            "tone": "warm",
            "key_points": ["be supportive"],
            "avoid": [],
        },
    }


def _call_parser(json_dict: dict) -> dict:
    """调用 LLMEmotionAnalyzer 的 LLM 输出解析方法。

    该方法将在 Task 11 中添加，当前不存在，因此会抛出 AttributeError。
    """
    return LLMEmotionAnalyzer.parse_affection_llm_output(json_dict)


# ═══════════════════════════════════════════════════════════════
# 测试类
# ═══════════════════════════════════════════════════════════════

class TestLLMOutputParsing:
    """LLM 输出解析的预期行为"""

    # ── 基础解析 ──────────────────────────────────────────────

    def test_valid_full_json(self):
        """完整的有效 JSON → 所有字段正确提取"""
        data = _make_valid_llm_json()
        result = _call_parser(data)

        # emotion_understanding
        assert result["emotion_understanding"] == "User seems happy"

        # emotional_needs
        assert result["emotional_needs"] == ["被理解"]

        # affection_impact
        assert result["affection_impact"]["direction"] == AffectionDirection.POSITIVE
        assert result["affection_impact"]["level"] == AffectionLevel.HIGH
        assert result["affection_impact"]["reason"] == "good vibes"

        # personality_shift
        assert result["personality_shift"]["trust"] == "up"
        assert result["personality_shift"]["dependence"] == "no_change"

        # response_guidance
        assert result["response_guidance"]["tone"] == "warm"
        assert result["response_guidance"]["key_points"] == ["be supportive"]
        assert result["response_guidance"]["avoid"] == []

    # ── 缺失字段 ──────────────────────────────────────────────

    def test_missing_affection_impact(self):
        """缺少 affection_impact → 默认中性方向/低等级/0 偏移"""
        data = _make_valid_llm_json()
        del data["affection_impact"]

        result = _call_parser(data)

        assert result["affection_impact"]["direction"] == AffectionDirection.NEUTRAL
        assert result["affection_impact"]["level"] == AffectionLevel.LOW
        assert result["affection_impact"]["reason"] == ""
        assert result["affection_impact"]["delta"] == 0.0

    def test_missing_personality_shift(self):
        """缺少 personality_shift → 所有维度默认 no_change"""
        data = _make_valid_llm_json()
        del data["personality_shift"]

        result = _call_parser(data)

        for dim in ("trust", "dependence", "openness", "jealousy"):
            assert result["personality_shift"][dim] == "no_change", (
                f"维度 {dim} 不是 no_change"
            )

    # ── 额外字段 ──────────────────────────────────────────────

    def test_extra_fields_ignored(self):
        """JSON 包含额外字段 → 不崩溃，额外字段被忽略"""
        data = _make_valid_llm_json()
        data["confidence"] = 0.95
        data["internal_note"] = "debug info"

        result = _call_parser(data)

        # 核心字段仍然存在
        assert result["emotion_understanding"] == "User seems happy"
        assert result["affection_impact"]["direction"] == AffectionDirection.POSITIVE
        # 不应存在意外键
        assert "confidence" not in result
        assert "internal_note" not in result

    # ── 无效输入 ──────────────────────────────────────────────

    def test_invalid_json(self):
        """LLM 返回非 JSON 文本 → fallback，情感回退 + 中性亲密度"""
        result = _call_parser("not json at all")

        # 解析器应该 fallback 到 EmotionAnalyzer + neutral affection
        assert isinstance(result["emotion"], EmotionType)
        assert result["affection_impact"]["direction"] == AffectionDirection.NEUTRAL
        assert result["affection_impact"]["level"] == AffectionLevel.LOW
        assert result["affection_impact"]["delta"] == 0.0

    def test_invalid_json_empty(self):
        """LLM 返回空字符串 → fallback"""
        result = _call_parser("")

        assert result["affection_impact"]["direction"] == AffectionDirection.NEUTRAL
        assert result["affection_impact"]["level"] == AffectionLevel.LOW

    # ── 边界方向/等级值 ──────────────────────────────────────

    def test_unknown_direction_value(self):
        """未知 direction 值 → 默认 NEUTRAL"""
        data = _make_valid_llm_json()
        data["affection_impact"]["direction"] = "quantum_happy"

        result = _call_parser(data)

        assert result["affection_impact"]["direction"] == AffectionDirection.NEUTRAL

    def test_unknown_level_value(self):
        """未知 level 值 → 默认 LOW"""
        data = _make_valid_llm_json()
        data["affection_impact"]["level"] = "extreme"

        result = _call_parser(data)

        assert result["affection_impact"]["level"] == AffectionLevel.LOW

    def test_direction_case_insensitive(self):
        """方向值大小写不敏感：POSITIVE / Positive / positive 都生效"""
        cases = ["POSITIVE", "Positive", "positive"]
        for case in cases:
            data = _make_valid_llm_json()
            data["affection_impact"]["direction"] = case

            result = _call_parser(data)

            assert result["affection_impact"]["direction"] == AffectionDirection.POSITIVE, (
                f"方向 '{case}' 无法正确解析为 POSITIVE"
            )

    # ── 边缘情况 ──────────────────────────────────────────────

    def test_emotion_understanding_long_text(self):
        """很长的 emotion_understanding 文本 → 不被截断"""
        long_text = "User mentioned that " + "very " * 100 + "long text"
        data = _make_valid_llm_json()
        data["emotion_understanding"] = long_text

        result = _call_parser(data)

        assert result["emotion_understanding"] == long_text

    def test_empty_emotional_needs(self):
        """emotional_needs 为空列表 → 不崩溃"""
        data = _make_valid_llm_json()
        data["emotional_needs"] = []

        result = _call_parser(data)

        assert result["emotional_needs"] == []

    def test_response_guidance_partial(self):
        """response_guidance 缺少某些键 → 默认空值填充"""
        data = _make_valid_llm_json()
        data["response_guidance"] = {
            "tone": "gentle",
            # 故意省略 key_points 和 avoid
        }

        result = _call_parser(data)

        assert result["response_guidance"]["tone"] == "gentle"
        assert result["response_guidance"]["key_points"] == []
        assert result["response_guidance"]["avoid"] == []
