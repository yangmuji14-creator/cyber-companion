"""亲密度管线集成测试 — 全流程测试

Tests-first (RED until Task 14):
- 当前 pipeline 使用 RelationshipTracker 管理亲密度
- Task 14 将改用 AffectionMapper + UnifiedAffectionStorage
- 本文件测试预期的最终行为，在 Task 14 之前应为 RED
"""

import sys
import os
import asyncio
import threading
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from core.chat.pipeline import ChatPipeline
from core.emotion import EmotionResult, EmotionType
from core.emotion.mood import MoodState, MoodType
from core.affection.constants import BASE_BONUS, AffectionDirection, AffectionLevel
from core.persona.models import Persona


# =============================================================================
# 辅助函数
# =============================================================================

def make_persona(persona_id: str = "test_persona", name: str = "测试人设",
                 rel_level: int = 50) -> Persona:
    """创建测试用 Persona 实例"""
    return Persona(
        id=persona_id,
        name=name,
        relationship_level=rel_level,
    )


def make_mock_pipeline(persona: Persona | None = None, temp_dir: str | None = None):
    """构建 ChatPipeline，所有外部依赖用 MagicMock 替代

    Returns:
        (pipeline, mocks_dict)
    """
    if persona is None:
        persona = make_persona()
    if temp_dir is None:
        temp_dir = tempfile.mkdtemp()

    data_dir = Path(temp_dir) / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    # --- LLM ---
    mock_llm = AsyncMock()
    mock_response = MagicMock()
    mock_response.content = "这是一个测试回复。"
    mock_llm.chat = AsyncMock(return_value=mock_response)

    # --- Memory Manager ---
    mock_memory_mgr = MagicMock()
    mock_memory_mgr.data_dir = data_dir
    mock_memory_mgr.get_context_prompt.return_value = ""
    mock_memory_mgr.get_memories.return_value = []

    # --- Persona Loader ---
    mock_persona_loader = MagicMock()
    mock_persona_loader.get.return_value = persona

    # --- Personality Engine ---
    mock_personality_engine = MagicMock()
    mock_personality_engine.get_state.return_value = {}
    mock_personality_engine.get_personality_context.return_value = ""

    # --- Chat History ---
    mock_chat_history = MagicMock()
    mock_chat_history.get_messages.return_value = []
    mock_chat_history.get_short_memories.return_value = []

    # --- LLM Emotion Analyzer (configured per test) ---
    mock_emotion_analyzer = MagicMock(spec=[])
    mock_emotion_analyzer._llm = None
    mock_emotion_analyzer.analyze = AsyncMock()
    mock_emotion_analyzer.trajectory = MagicMock()

    # --- Relationship Tracker (保留用于向后兼容) ---
    mock_relationship_tracker = MagicMock()
    mock_relationship_tracker.update.return_value = 50
    mock_relationship_tracker.get_level.return_value = 50

    # --- Unified Affection Storage (v3.0) ---
    mock_affection_storage = MagicMock()
    mock_affection_storage.apply_decay.return_value = 50.0
    mock_affection_storage.update.return_value = 50.0
    mock_affection_storage.get_level.return_value = 50.0

    # --- Mood Engine ---
    mock_mood_engine = MagicMock()
    mock_mood_engine.get_mood.return_value = MoodState(
        mood=MoodType.NEUTRAL,
        energy=0.5,
    )

    # --- Dialogue Thinker ---
    mock_dialogue_thinker = AsyncMock()
    mock_dialogue_thinker.think.return_value = None

    # --- Topic Tracker ---
    mock_topic_tracker = MagicMock()
    mock_topic_tracker.get_topic_context.return_value = ""

    # --- 构建 pipeline ---
    pipeline = ChatPipeline(
        llm=mock_llm,
        memory_mgr=mock_memory_mgr,
        persona_loader=mock_persona_loader,
        personality_engine=mock_personality_engine,
        chat_history=mock_chat_history,
        llm_emotion_analyzer=mock_emotion_analyzer,
        relationship_tracker=mock_relationship_tracker,
        mood_manager=mock_mood_engine,
        config={},
        dialogue_thinker=mock_dialogue_thinker,
        consistency_guard=MagicMock(),
        topic_tracker=mock_topic_tracker,
        affection_storage=mock_affection_storage,
    )

    mocks = {
        "llm": mock_llm,
        "memory_mgr": mock_memory_mgr,
        "persona_loader": mock_persona_loader,
        "personality_engine": mock_personality_engine,
        "chat_history": mock_chat_history,
        "emotion_analyzer": mock_emotion_analyzer,
        "relationship_tracker": mock_relationship_tracker,
        "affection_storage": mock_affection_storage,
        "mood_engine": mock_mood_engine,
        "dialogue_thinker": mock_dialogue_thinker,
        "topic_tracker": mock_topic_tracker,
    }
    return pipeline, mocks


def run_async(coro):
    """在同步测试中执行异步协程"""
    return asyncio.run(coro)


# =============================================================================
# 测试辅助：简化版内存亲密度存储（模拟 UnifiedAffectionStorage 的行为）
# 用于 concurrent 测试；Task 14 后应替换为真正的 UnifiedAffectionStorage
# =============================================================================

class _InMemoryAffectionStore:
    """线程安全的内存亲密度存储（模拟未来 UnifiedAffectionStorage 接口）"""

    def __init__(self, initial: float = 50.0):
        self._level = initial
        self._lock = threading.Lock()

    def update(self, delta: float) -> float:
        with self._lock:
            self._level += delta
            self._level = max(0.0, min(100.0, self._level))
            return self._level

    @property
    def level(self) -> float:
        with self._lock:
            return self._level


# =============================================================================
# TestPipelineIntegration
# =============================================================================

class TestPipelineIntegration:
    """完整管线集成测试：情绪分析 → 亲密度变化"""

    def test_full_pipeline_flow(self):
        """Mock LLMEmotionAnalyzer 返回已知输出 → 验证亲密度变化"""
        pipeline, mocks = make_mock_pipeline()

        emotion_result = EmotionResult(
            emotion=EmotionType.HAPPY, intensity=0.8, keywords=["开心"],
        )
        enriched = {
            "emotion_understanding": "用户很开心",
            "emotional_needs": [],
            "affection_impact": {"direction": "positive", "level": "medium", "reason": "开心"},
            "personality_shift": {"trust": "up", "dependence": "no_change"},
            "response_guidance": {"tone": "warm", "key_points": [], "avoid": []},
        }
        mocks["emotion_analyzer"].analyze.return_value = (emotion_result, enriched)
        mocks["affection_storage"].update.return_value = 55.0

        reply, level = run_async(pipeline.process(
            user_id="test_user",
            content="今天好开心！",
            persona_id="test_persona",
        ))

        # 情绪分析被调用
        mocks["emotion_analyzer"].analyze.assert_awaited_once_with("今天好开心！")

        # affection_storage.update 被调用
        mocks["affection_storage"].update.assert_called_once()
        call_kwargs = mocks["affection_storage"].update.call_args.kwargs
        assert call_kwargs.get("direction") == "positive"
        assert call_kwargs.get("level") == "medium"
        assert call_kwargs.get("persona_id") == "test_persona"

        # 返回值是 update 返回的 level
        assert level == 55

    def test_positive_message_increases_affection(self):
        """Mock HAPPY 情绪 → 亲密度上升"""
        pipeline, mocks = make_mock_pipeline()

        emotion_result = EmotionResult(
            emotion=EmotionType.HAPPY, intensity=0.9, keywords=["开心"],
        )
        enriched = {
            "emotion_understanding": "用户很开心",
            "emotional_needs": [],
            "affection_impact": {"direction": "positive", "level": "high", "reason": "开心"},
            "personality_shift": {"trust": "up", "dependence": "up"},
            "response_guidance": {"tone": "warm", "key_points": [], "avoid": []},
        }
        mocks["emotion_analyzer"].analyze.return_value = (emotion_result, enriched)
        mocks["affection_storage"].update.return_value = 53.0

        reply, level = run_async(pipeline.process(
            user_id="test_user",
            content="太棒了！",
            persona_id="test_persona",
        ))

        assert level > 50  # 亲密度应该上升
        mocks["affection_storage"].update.assert_called_once()
        call_kwargs = mocks["affection_storage"].update.call_args.kwargs
        assert call_kwargs["direction"] == "positive"

    def test_negative_message_decreases_affection(self):
        """Mock ANGRY 情绪 → 亲密度下降"""
        pipeline, mocks = make_mock_pipeline()

        emotion_result = EmotionResult(
            emotion=EmotionType.ANGRY, intensity=0.7, keywords=["生气"],
        )
        enriched = {
            "emotion_understanding": "用户很生气",
            "emotional_needs": ["需要冷静"],
            "affection_impact": {"direction": "negative", "level": "high", "reason": "生气"},
            "personality_shift": {"trust": "down", "jealousy": "up"},
            "response_guidance": {"tone": "gentle", "key_points": ["安抚"], "avoid": ["争辩"]},
        }
        mocks["emotion_analyzer"].analyze.return_value = (emotion_result, enriched)
        mocks["affection_storage"].update.return_value = 48.0

        reply, level = run_async(pipeline.process(
            user_id="test_user",
            content="真让人生气！",
            persona_id="test_persona",
        ))

        assert level < 50  # 亲密度应该下降
        mocks["affection_storage"].update.assert_called_once()
        call_kwargs = mocks["affection_storage"].update.call_args.kwargs
        assert call_kwargs["direction"] == "negative"

    def test_neutral_message_gets_base_bonus(self):
        """Mock NEUTRAL → 亲密度按 BASE_BONUS (0.02) 增长"""
        pipeline, mocks = make_mock_pipeline()

        emotion_result = EmotionResult(
            emotion=EmotionType.NEUTRAL, intensity=0.1, keywords=[],
        )
        enriched = {
            "emotion_understanding": "",
            "emotional_needs": [],
            "affection_impact": {"direction": "neutral", "level": "low", "reason": ""},
            "personality_shift": {},
            "response_guidance": {"tone": "", "key_points": [], "avoid": []},
        }
        mocks["emotion_analyzer"].analyze.return_value = (emotion_result, enriched)
        mocks["affection_storage"].update.return_value = 50.0

        reply, level = run_async(pipeline.process(
            user_id="test_user",
            content="今天天气不错。",
            persona_id="test_persona",
        ))

        mocks["affection_storage"].update.assert_called_once()
        call_kwargs = mocks["affection_storage"].update.call_args.kwargs
        assert call_kwargs["direction"] == "neutral"

        # 当 UnifiedAffectionStorage 集成后，中性消息会自动加上 BASE_BONUS (0.02)
        # 在存储层内部处理，管线只负责传递 direction 和 level

    def test_command_skips_affection(self):
        """发送 /command → 跳过 LLM 分析，亲密度不变

        Pipeline 检测以 '/' 开头的内容，
        跳过情绪分析和亲密度更新，直接返回回复。
        """
        pipeline, mocks = make_mock_pipeline()

        reply, level = run_async(pipeline.process(
            user_id="test_user",
            content="/stats",
            persona_id="test_persona",
        ))

        # 命令应跳过情绪分析
        mocks["emotion_analyzer"].analyze.assert_not_awaited()
        # 命令不应更新亲密度
        mocks["affection_storage"].update.assert_not_called()
        # 命令应返回当前亲密度
        assert level == 50


# =============================================================================
# TestPipelineEdgeCases
# =============================================================================

class TestPipelineEdgeCases:
    """管线边界条件：空消息、空白消息、人设切换"""

    def test_empty_message_skipped(self):
        """发送空字符串 → pipeline 提前返回，无亲密度变化

        Pipeline 检测 content 为 '' 时直接返回，
        不调用 LLM 分析、不更新亲密度。
        """
        pipeline, mocks = make_mock_pipeline()

        reply, level = run_async(pipeline.process(
            user_id="test_user",
            content="",
            persona_id="test_persona",
        ))

        # 空消息应跳过
        mocks["emotion_analyzer"].analyze.assert_not_awaited()
        mocks["affection_storage"].update.assert_not_called()
        assert reply == ""

    def test_whitespace_message_skipped(self):
        """发送全空白字符串 → pipeline 跳过，不更新亲密度

        Pipeline 检测 strip() 后为空的内容并跳过。
        """
        pipeline, mocks = make_mock_pipeline()

        reply, level = run_async(pipeline.process(
            user_id="test_user",
            content="   ",
            persona_id="test_persona",
        ))

        # 空白消息应跳过
        mocks["emotion_analyzer"].analyze.assert_not_awaited()
        mocks["affection_storage"].update.assert_not_called()
        assert reply == ""

    def test_persona_switch_preserves_affection(self):
        """切换人设后，不同人设应保持各自的亲密度值

        AffectionMapper 接受的 persona_id 参数应使
        不同人设的同一用户拥有独立的亲密度值。
        """
        pipeline, mocks = make_mock_pipeline()

        emotion_result = EmotionResult(
            emotion=EmotionType.HAPPY, intensity=0.8, keywords=[],
        )
        enriched = {
            "emotion_understanding": "用户打招呼",
            "emotional_needs": [],
            "affection_impact": {"direction": "positive", "level": "low", "reason": "打招呼"},
            "personality_shift": {},
            "response_guidance": {"tone": "warm", "key_points": [], "avoid": []},
        }
        mocks["emotion_analyzer"].analyze.return_value = (emotion_result, enriched)

        # affection_storage 为不同 persona_id 返回不同值
        def storage_update_side_effect(user_id, **kwargs):
            pid = kwargs.get("persona_id", "default")
            if pid == "persona_a":
                return 55.0
            elif pid == "persona_b":
                return 60.0
            return 50.0

        mocks["affection_storage"].update.side_effect = storage_update_side_effect

        # 使用 persona_a
        reply_a, level_a = run_async(pipeline.process(
            user_id="test_user",
            content="你好呀",
            persona_id="persona_a",
        ))

        # 使用 persona_b
        reply_b, level_b = run_async(pipeline.process(
            user_id="test_user",
            content="今天怎么样",
            persona_id="persona_b",
        ))

        # 不同人设应有不同的亲密度值
        assert level_a == 55
        assert level_b == 60
        assert level_a != level_b


# =============================================================================
# TestConcurrentWrites
# =============================================================================

class TestConcurrentWrites:
    """并发写入测试：线程安全的亲密度更新"""

    def test_concurrent_updates(self):
        """10 个线程并发更新同一用户 → 最终值应为所有增量的正确总和

        每个线程增加 1.0，总计 +10.0，初始 50.0 → 期望 60.0。
        """
        store = _InMemoryAffectionStore(initial=50.0)
        n_threads = 10
        delta_per_thread = 1.0
        barrier = threading.Barrier(n_threads)  # 确保最大并发
        errors = []

        def worker():
            try:
                barrier.wait()  # 所有线程同时释放
                store.update(delta_per_thread)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"并发更新出现异常: {errors}"
        # 10 * 1.0 + 50.0 = 60.0
        assert store.level == 60.0, (
            f"期望 60.0，实际 {store.level} — 可能发生了丢失更新"
        )

    def test_concurrent_positive_negative_mixed(self):
        """并发混合正负更新 → 最终值正确（不丢失更新）

        5 个线程 +2.0，5 个线程 -1.0
        总计 (+10.0) + (-5.0) = +5.0
        初始 50.0 → 期望 55.0
        """
        store = _InMemoryAffectionStore(initial=50.0)
        barrier = threading.Barrier(10)
        errors = []

        def worker_positive():
            try:
                barrier.wait()
                store.update(2.0)
            except Exception as e:
                errors.append(e)

        def worker_negative():
            try:
                barrier.wait()
                store.update(-1.0)
            except Exception as e:
                errors.append(e)

        threads = []
        for _ in range(5):
            threads.append(threading.Thread(target=worker_positive))
        for _ in range(5):
            threads.append(threading.Thread(target=worker_negative))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        # (5 * 2.0) + (5 * -1.0) + 50.0 = 10.0 - 5.0 + 50.0 = 55.0
        assert store.level == 55.0, (
            f"期望 55.0，实际 {store.level} — 可能丢失了更新"
        )

    def test_concurrent_with_clamp(self):
        """并发更新接近边界时，不超限

        10 个线程各 +10.0，初始 95.0
        理论 195.0 → clamped 到 100.0
        验证最终值 = 100.0 且无异常
        """
        store = _InMemoryAffectionStore(initial=95.0)
        n_threads = 10
        barrier = threading.Barrier(n_threads)
        errors = []

        def worker():
            try:
                barrier.wait()
                store.update(10.0)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert store.level == 100.0, (
            f"期望 clamped 到 100.0，实际 {store.level}"
        )


# =============================================================================
# 运行入口
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
