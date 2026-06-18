"""LLM 情感分析器降级回退行为测试

测试策略：
- LLM 超时/错误 → 回退到 EmotionAnalyzer 关键词匹配
- 连续失败 → 降级（跳过 enrichment）
- 恢复后 → 回到正常状态

NOTE: 降级相关测试（TestDegradationState + test_consecutive_failures_degrade
+ test_recovery_after_degrade）是测试先行（TDD RED 阶段），
当前代码尚无 _failure_count / _degraded 逻辑。
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest

from core.emotion.analyzer import EmotionAnalyzer, EmotionType, EmotionResult
from core.emotion.llm_analyzer import LLMEmotionAnalyzer
from core.llm.base import LLMResponse


# ===================================================================
# 辅助工厂
# ===================================================================

def _make_mock_llm(chat_return=None, chat_raise=None):
    """创建一个可注入 LLMEmotionAnalyzer 的 mock LLM。

    Args:
        chat_return: 如果设置，``chat()`` 返回该值。
        chat_raise:  如果设置，``chat()`` 抛出该异常（优先级高于 return）。
    """
    mock = MagicMock()
    mock.chat = AsyncMock()
    if chat_raise:
        mock.chat.side_effect = chat_raise
    elif chat_return is not None:
        mock.chat.return_value = chat_return
    else:
        mock.chat.return_value = LLMResponse(
            content='{"emotion": "\u4e2d\u6027", "intensity": 0.0, "reason": ""}',
            model="mock",
        )

    # 满足 _llm 的 truthiness 检查
    mock.chat.__class__ = AsyncMock
    return mock


def _make_analyzer(llm=None):
    """快速构造 LLMEmotionAnalyzer，可选注入 mock LLM。"""
    return LLMEmotionAnalyzer(llm=llm)


async def _analyze(analyzer, text: str):
    """同步包装器：在 sync 测试函数中调用 async analyze。"""
    return await analyzer.analyze(text)


# ===================================================================
# TestFallbackBehavior
# ===================================================================

class TestFallbackBehavior:
    """LLM 失败时的回退行为"""

    def test_llm_timeout_fallback(self):
        """LLM 超时 → 回退到 EmotionAnalyzer 关键词匹配 → NEUTRAL + 0 强度"""
        mock_llm = _make_mock_llm(chat_raise=TimeoutError("LLM timed out"))
        analyzer = _make_analyzer(mock_llm)

        result, enriched = asyncio.run(analyzer.analyze("嗯"))

        # LLM 失败的后果：走 EmotionAnalyzer 关键词分析
        # "嗯" 无匹配关键词 → 中性 + 0.0
        assert result.emotion == EmotionType.NEUTRAL
        assert result.intensity == 0.0
        assert result.keywords == []

    def test_llm_non_json_fallback(self):
        """LLM 返回非 JSON 纯文本 → 回退到关键词分析"""
        mock_llm = _make_mock_llm(
            chat_return=LLMResponse(content="I don't know", model="mock")
        )
        analyzer = _make_analyzer(mock_llm)

        result, enriched = asyncio.run(analyzer.analyze("我好开心呀"))

        # parse_json_response 失败 → fallback → EmotionAnalyzer 检出「开心」
        assert result.emotion == EmotionType.HAPPY

    def test_llm_error_response(self):
        """LLM 返回有效 JSON（含 error 信息）→ 视为有效 JSON，不走 fallback"""
        mock_llm = _make_mock_llm(
            chat_return=LLMResponse(
                content='{"emotion": "中性", "intensity": 0.3, "reason": "API internal error"}',
                model="mock",
            )
        )
        analyzer = _make_analyzer(mock_llm)

        result, enriched = asyncio.run(analyzer.analyze("今天天气不错"))

        # parse_json_response 成功 → 不走 fallback → emotion/intensity 来自 LLM 响应
        assert result.emotion == EmotionType.NEUTRAL
        assert result.intensity == 0.3
        # 关键词应包含 LLM 的 reason
        assert any("API internal error" in kw for kw in result.keywords)

    def test_consecutive_failures_degrade(self):
        """连续 3 次 LLM 失败 → analyzer 降级（跳过 enrichment）"""
        mock_llm = _make_mock_llm(chat_raise=TimeoutError("timeout"))
        analyzer = _make_analyzer(mock_llm)

        # 连续 3 次失败
        for _ in range(3):
            asyncio.run(analyzer.analyze("测试消息"))

        # 降级标记应当被设置（TDD RED：此字段尚不存在）
        assert analyzer._degraded is True  # type: ignore[attr-defined]

    def test_recovery_after_degrade(self):
        """降级后 LLM 恢复工作 → 回到正常"""
        call_count = 0

        async def _chat_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                raise TimeoutError("timeout")
            return LLMResponse(
                content='{"emotion": "\u5f00\u5fc3", "intensity": 0.8, "reason": "felt happy"}',
                model="mock",
            )

        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(side_effect=_chat_side_effect)
        analyzer = _make_analyzer(mock_llm)

        # 3 次失败 → 降级
        for _ in range(3):
            asyncio.run(analyzer.analyze("测试"))
        # 第 4 次成功 → 恢复
        result, enriched = asyncio.run(analyzer.analyze("今天好开心"))

        # 降级应被解除，LLM 响应被使用
        assert analyzer._degraded is False  # type: ignore[attr-defined]
        assert result.emotion == EmotionType.HAPPY
        assert result.intensity == 0.8

    def test_keyword_fallback_emotion(self):
        """LLM 失败时 EmotionAnalyzer 仍能检出情感关键词"""
        mock_llm = _make_mock_llm(chat_raise=ConnectionError("LLM offline"))
        analyzer = _make_analyzer(mock_llm)

        result, enriched = asyncio.run(analyzer.analyze("我好难过啊"))

        # 回退 → 关键词「难过」→ SAD
        assert result.emotion == EmotionType.SAD
        assert "难过" in result.keywords

    def test_keyword_fallback_neutral(self):
        """LLM 失败且无关键词匹配 → NEUTRAL + 0 affection change"""
        mock_llm = _make_mock_llm(chat_raise=RuntimeError("LLM crash"))
        analyzer = _make_analyzer(mock_llm)

        result, enriched = asyncio.run(analyzer.analyze("今天星期二"))

        # 无情感关键词 → 中性 + 0.0
        assert result.emotion == EmotionType.NEUTRAL
        assert result.intensity == 0.0
        assert result.keywords == []


# ===================================================================
# TestDegradationState
# ===================================================================

class TestDegradationState:
    """降级状态追踪（TDD RED：以下字段当前均不存在）"""

    def test_failure_count_tracking(self):
        """analyzer 追踪连续失败次数"""
        mock_llm = _make_mock_llm(chat_raise=TimeoutError("timeout"))
        analyzer = _make_analyzer(mock_llm)

        _ = asyncio.run(analyzer.analyze("A"))
        # 1 次失败后 count == 1
        assert analyzer._failure_count == 1  # type: ignore[attr-defined]

        _ = asyncio.run(analyzer.analyze("B"))
        # 2 次失败后 count == 2
        assert analyzer._failure_count == 2  # type: ignore[attr-defined]

        _ = asyncio.run(analyzer.analyze("C"))
        # 3 次失败后 count == 3
        assert analyzer._failure_count == 3  # type: ignore[attr-defined]

    def test_degrade_flag(self):
        """连续 3 次失败后 degrade 标记置位"""
        mock_llm = _make_mock_llm(chat_raise=TimeoutError("timeout"))
        analyzer = _make_analyzer(mock_llm)

        # 尚未触发降级
        for _ in range(2):
            asyncio.run(analyzer.analyze("X"))
        assert analyzer._degraded is False  # type: ignore[attr-defined]

        # 第 3 次 → 降级
        asyncio.run(analyzer.analyze("X"))
        assert analyzer._degraded is True  # type: ignore[attr-defined]

    def test_degrade_reset_on_success(self):
        """成功调用后失败计数器重置"""
        call_sequence = [
            TimeoutError("no"),        # 1: fail
            TimeoutError("no"),        # 2: fail
            LLMResponse(content='{"emotion": "\u5f00\u5fc3", "intensity": 0.5, "reason": "joy"}', model="mock"),  # 3: success
        ]
        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(side_effect=call_sequence)
        analyzer = _make_analyzer(mock_llm)

        # 2 次失败
        asyncio.run(analyzer.analyze("A"))
        asyncio.run(analyzer.analyze("B"))
        assert analyzer._failure_count == 2  # type: ignore[attr-defined]

        # 成功调用 → 重置
        asyncio.run(analyzer.analyze("C"))
        assert analyzer._failure_count == 0  # type: ignore[attr-defined]
