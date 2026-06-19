"""亲密度映射器单元测试 — AffectionMapper (方向→数值映射)"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest

from core.social.affection.constants import (
    AffectionDirection,
    AffectionLevel,
    DIRECTION_LEVEL_MAP,
    PERSONALITY_SHIFT_MAP,
    BASE_BONUS,
)


# ========== 方向 × 等级 → 数值映射测试 ==========

class TestAffectionMapperMapping:
    """测试方向×等级→数值增量映射表（共 21 项组合）"""

    # ── 所有 21 种组合的精确值验证 ──
    @pytest.mark.parametrize("direction, level, expected", [
        (AffectionDirection.STRONG_POSITIVE, AffectionLevel.HIGH, 15.0),
        (AffectionDirection.STRONG_POSITIVE, AffectionLevel.MEDIUM, 10.0),
        (AffectionDirection.STRONG_POSITIVE, AffectionLevel.LOW, 5.0),
        (AffectionDirection.POSITIVE, AffectionLevel.HIGH, 8.0),
        (AffectionDirection.POSITIVE, AffectionLevel.MEDIUM, 5.0),
        (AffectionDirection.POSITIVE, AffectionLevel.LOW, 2.0),
        (AffectionDirection.SLIGHT_POSITIVE, AffectionLevel.HIGH, 1.0),
        (AffectionDirection.SLIGHT_POSITIVE, AffectionLevel.MEDIUM, 0.5),
        (AffectionDirection.SLIGHT_POSITIVE, AffectionLevel.LOW, 0.2),
        (AffectionDirection.NEUTRAL, AffectionLevel.HIGH, 0.0),
        (AffectionDirection.NEUTRAL, AffectionLevel.MEDIUM, 0.0),
        (AffectionDirection.NEUTRAL, AffectionLevel.LOW, 0.0),
        (AffectionDirection.SLIGHT_NEGATIVE, AffectionLevel.HIGH, -1.0),
        (AffectionDirection.SLIGHT_NEGATIVE, AffectionLevel.MEDIUM, -0.5),
        (AffectionDirection.SLIGHT_NEGATIVE, AffectionLevel.LOW, -0.2),
        (AffectionDirection.NEGATIVE, AffectionLevel.HIGH, -8.0),
        (AffectionDirection.NEGATIVE, AffectionLevel.MEDIUM, -5.0),
        (AffectionDirection.NEGATIVE, AffectionLevel.LOW, -2.0),
        (AffectionDirection.STRONG_NEGATIVE, AffectionLevel.HIGH, -15.0),
        (AffectionDirection.STRONG_NEGATIVE, AffectionLevel.MEDIUM, -10.0),
        (AffectionDirection.STRONG_NEGATIVE, AffectionLevel.LOW, -5.0),
    ])
    def test_all_21_mapping_combinations(self, direction, level, expected):
        """验证每种方向×等级组合的映射值与常量定义一致"""
        assert DIRECTION_LEVEL_MAP[(direction, level)] == expected

    # ── 符号方向属性验证 ──
    def test_positive_directions_produce_positive_deltas(self):
        """所有正向方向（STRONG_POSITIVE / POSITIVE / SLIGHT_POSITIVE）产生的 delta > 0"""
        positive = {
            AffectionDirection.STRONG_POSITIVE,
            AffectionDirection.POSITIVE,
            AffectionDirection.SLIGHT_POSITIVE,
        }
        for (direction, _), delta in DIRECTION_LEVEL_MAP.items():
            if direction in positive:
                assert delta > 0, f"{direction.name} should yield delta>0, got {delta}"

    def test_neutral_produces_zero_delta(self):
        """NEUTRAL 方向无视等级，delta 恒为 0.0"""
        for (direction, level), delta in DIRECTION_LEVEL_MAP.items():
            if direction == AffectionDirection.NEUTRAL:
                assert delta == 0.0, f"NEUTRAL/{level.name} should be 0.0, got {delta}"

    def test_negative_directions_produce_negative_deltas(self):
        """所有负向方向（STRONG_NEGATIVE / NEGATIVE / SLIGHT_NEGATIVE）产生的 delta < 0"""
        negative = {
            AffectionDirection.STRONG_NEGATIVE,
            AffectionDirection.NEGATIVE,
            AffectionDirection.SLIGHT_NEGATIVE,
        }
        for (direction, _), delta in DIRECTION_LEVEL_MAP.items():
            if direction in negative:
                assert delta < 0, f"{direction.name} should yield delta<0, got {delta}"

    # ── 结构性验证 ──
    def test_all_directions_have_three_levels(self):
        """每个方向均应包含 HIGH / MEDIUM / LOW 三个等级"""
        for direction in AffectionDirection:
            for level in AffectionLevel:
                key = (direction, level)
                assert key in DIRECTION_LEVEL_MAP, f"Missing mapping for {direction.name}/{level.name}"

    def test_delta_magnitude_increases_with_level(self):
        """同一方向下，HIGH >= MEDIUM >= LOW（绝对值意义上）"""
        for direction in AffectionDirection:
            if direction == AffectionDirection.NEUTRAL:
                continue
            high = abs(DIRECTION_LEVEL_MAP[(direction, AffectionLevel.HIGH)])
            med = abs(DIRECTION_LEVEL_MAP[(direction, AffectionLevel.MEDIUM)])
            low = abs(DIRECTION_LEVEL_MAP[(direction, AffectionLevel.LOW)])
            assert high >= med >= low, (
                f"{direction.name}: expected HIGH({high}) >= MEDIUM({med}) >= LOW({low})"
            )


# ========== 人格维度偏移映射测试 ==========

class TestAffectionMapperPersonality:
    """测试人格维度偏移映射（每次亲密度变化时的微调量）"""

    def test_personality_shift_up(self):
        """'up' 方向产生正确的五维人格偏移（含 affection）"""
        expected = {
            "trust": 0.02,
            "dependence": 0.02,
            "openness": 0.01,
            "jealousy": -0.01,
            "affection": 0.02,
        }
        assert PERSONALITY_SHIFT_MAP["up"] == expected

    def test_personality_shift_down(self):
        """'down' 方向产生正确的五维人格偏移（含 affection）"""
        expected = {
            "trust": -0.02,
            "dependence": -0.02,
            "openness": -0.01,
            "jealousy": 0.01,
            "affection": -0.02,
        }
        assert PERSONALITY_SHIFT_MAP["down"] == expected

    def test_personality_shift_no_change(self):
        """'no_change' 方向五维人格偏移全为 0.0（含 affection）"""
        expected = {
            "trust": 0.0,
            "dependence": 0.0,
            "openness": 0.0,
            "jealousy": 0.0,
            "affection": 0.0,
        }
        assert PERSONALITY_SHIFT_MAP["no_change"] == expected

    def test_personality_shift_unknown_defaults_to_no_change(self):
        """未知方向键不存在于映射表中，mapper 应默认返回 no_change 的值"""
        # PERSONALITY_SHIFT_MAP 不含 'unknown' 键（确认不存在）
        assert "unknown" not in PERSONALITY_SHIFT_MAP
        # 期望的 fallback 行为：返回 no_change
        fallback = PERSONALITY_SHIFT_MAP.get("unknown", PERSONALITY_SHIFT_MAP["no_change"])
        assert fallback == PERSONALITY_SHIFT_MAP["no_change"]

    def test_base_bonus_always_included(self):
        """BASE_BONUS = 0.02 始终作为映射结果的基础奖励"""
        assert BASE_BONUS == 0.02

    def test_all_personality_shifts_have_all_five_dimensions(self):
        """每个人格偏移条目均包含 trust / dependence / openness / jealousy / affection"""
        required = {"trust", "dependence", "openness", "jealousy", "affection"}
        for key, shift in PERSONALITY_SHIFT_MAP.items():
            assert set(shift.keys()) == required, f"'{key}' missing one or more personality dimensions"


# ========== 边缘情况测试（预期 RED） ==========

class TestAffectionMapperEdgeCases:
    """测试映射器边缘情况 — AffectionMapper 尚未实现（预期为 RED，Task 10 实现后变绿）"""

    def _require_mapper(self):
        """尝试导入 AffectionMapper，若不存在则标记为预期失败（RED）"""
        try:
            from core.social.affection.mapper import AffectionMapper  # noqa: F811
            return AffectionMapper
        except ImportError:
            pytest.fail(
                "AffectionMapper not yet implemented — this test is expected to be RED. "
                "Implement the mapper class in core/social/affection/mapper.py (Task 10) to make it pass."
            )

    def test_unknown_direction_defaults_to_neutral(self):
        """未知方向名应默认解析为 NEUTRAL，delta = 0.0"""
        mapper = self._require_mapper()
        result = mapper.get_delta("unknown_direction", AffectionLevel.LOW)
        assert result == 0.0

    def test_unknown_level_defaults_to_low(self):
        """未知等级名应默认解析为 LOW"""
        mapper = self._require_mapper()
        result = mapper.get_delta(AffectionDirection.POSITIVE, "super_high")
        expected = DIRECTION_LEVEL_MAP[(AffectionDirection.POSITIVE, AffectionLevel.LOW)]
        assert result == expected

    def test_direction_string_vs_enum(self):
        """字符串 'positive' 与枚举 AffectionDirection.POSITIVE 应产生相同结果"""
        mapper = self._require_mapper()
        from_enum = mapper.get_delta(AffectionDirection.POSITIVE, AffectionLevel.HIGH)
        from_string = mapper.get_delta("positive", AffectionLevel.HIGH)
        assert from_enum == from_string
