"""Tests for the brain module — StateCollector"""

from __future__ import annotations

import pytest
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, PropertyMock

from core.brain.checker import CharacterBreakDetector, CharacterBreakResult
from core.brain.collector import StateCollector
from core.brain.models import BrainInput, MonologueThought
from core.brain.organizer import ThoughtOrganizer


# =============================================================================
# Fixtures: mock subsystems
# =============================================================================


@pytest.fixture
def mock_mood_engine():
    engine = MagicMock()
    mood_state = MagicMock()
    mood_state.mood.value = "happy"
    mood_state.valence = 0.8
    mood_state.arousal = 0.6
    mood_state.energy = 0.7
    mood_state.intensity = 0.5
    engine.get_mood.return_value = mood_state
    return engine


@pytest.fixture
def mock_open_loop_engine():
    engine = MagicMock()
    engine.get_context.return_value = (
        "【用户正在经历的事情】\n"
        "- 下周面试（待完成）\n"
        "- 项目开发（待完成）"
    )
    return engine


@pytest.fixture
def mock_topic_tracker():
    tracker = MagicMock()
    tracker.get_current_topic.return_value = "工作"
    tracker.get_all_topics.return_value = ["工作", "面试", "周末"]
    return tracker


@pytest.fixture
def mock_chat_history():
    storage = MagicMock()
    storage.get_messages.return_value = [
        {"role": "user", "content": "今天好累", "emotion": "tired", "emotion_intensity": 0.7},
        {"role": "assistant", "content": "辛苦啦"},
        {"role": "user", "content": "面试感觉还不错", "emotion": "happy", "emotion_intensity": 0.8},
    ]
    return storage


@pytest.fixture
def mock_personality_engine():
    engine = MagicMock()
    state = MagicMock()
    state.trust = 0.7
    state.dependence = 0.5
    state.openness = 0.6
    state.affection = 0.4
    state.jealousy = 0.3
    engine.get_state.return_value = state
    return engine


@pytest.fixture
def mock_affection_storage():
    storage = MagicMock()
    storage.get_level.return_value = 65.0
    stats = MagicMock()
    stats.days_known = 30
    storage.get_stats.return_value = stats
    return storage


@pytest.fixture
def mock_identity():
    identity = MagicMock()
    identity.get_context.return_value = (
        "【用户身份档案】\n"
        "- 教育背景：计算机专业\n"
        "- 兴趣：编程、游戏"
    )
    return identity


@pytest.fixture
def mock_life_summary():
    engine = MagicMock()
    engine.get_context.return_value = (
        "【用户长期画像】\n"
        "近期状态：正在找工作\n"
        "当前目标：拿到好的 offer"
    )
    return engine


@pytest.fixture
def mock_persona_loader():
    loader = MagicMock()
    persona = MagicMock()
    persona.name = "小雨"
    persona.personality = ["温柔", "活泼", "粘人"]
    loader.get.return_value = persona
    return loader


@pytest.fixture
def mock_drift_monitor():
    monitor = MagicMock()
    # No state to report — simulate a clean monitor
    return monitor


@pytest.fixture
def mock_proactive_messenger():
    messenger = MagicMock()
    type(messenger)._fired_today = PropertyMock(
        return_value={"morning": datetime.now(), "evening": datetime.now()}
    )
    return messenger


# =============================================================================
# Tests
# =============================================================================


class TestStateCollector:
    """StateCollector tests"""

    @pytest.mark.asyncio
    async def test_state_collector_collect(
        self,
        mock_mood_engine,
        mock_open_loop_engine,
        mock_topic_tracker,
        mock_chat_history,
        mock_personality_engine,
        mock_affection_storage,
        mock_identity,
        mock_life_summary,
        mock_persona_loader,
        mock_drift_monitor,
        mock_proactive_messenger,
    ):
        """Test that collect() gathers state from all 12 configurable subsystems
        (plus time context and user emotion which are always available)."""
        collector = StateCollector(
            mood_engine=mock_mood_engine,
            open_loop_engine=mock_open_loop_engine,
            topic_tracker=mock_topic_tracker,
            chat_history=mock_chat_history,
            personality_engine=mock_personality_engine,
            affection_storage=mock_affection_storage,
            identity=mock_identity,
            life_summary=mock_life_summary,
            persona_loader=mock_persona_loader,
            drift_monitor=mock_drift_monitor,
            proactive_messenger=mock_proactive_messenger,
        )

        result = await collector.collect("test_user", "girlfriend_001")

        # Type check
        assert isinstance(result, BrainInput)

        # === Mood ===
        assert result.mood_type == "happy"
        assert result.mood_valence == 0.8
        assert result.mood_arousal == 0.6
        assert result.mood_energy == 0.7
        assert result.mood_intensity == 0.5

        # === Dialogue Thought ===
        # No dialogue_thinker passed, so None
        assert result.dialogue_thought is None

        # === OpenLoop ===
        assert result.openloop_events is not None
        assert "下周面试" in result.openloop_events[0]

        # === Topic ===
        assert result.current_topic == "工作"
        assert result.topic_keywords == ["工作", "面试", "周末"]

        # === Chat History ===
        assert result.chat_history_summary is not None
        assert "[user]" in result.chat_history_summary

        # === Personality ===
        assert result.personality_trust == 0.7
        assert result.personality_dependence == 0.5
        assert result.personality_openness == 0.6
        assert result.personality_affection == 0.4
        assert result.personality_jealousy == 0.3

        # === Affection ===
        assert result.affection_level == 65.0
        assert result.affection_days_known == 30

        # === Identity ===
        assert result.identity_context is not None
        assert "计算机" in result.identity_context

        # === Life Summary ===
        assert result.life_summary is not None
        assert "找工作" in result.life_summary

        # === Persona ===
        assert result.persona_name == "小雨"
        assert result.persona_traits == ["温柔", "活泼", "粘人"]

        # === Drift ===
        # No report since mock has no state
        # Just ensure it doesn't crash
        _ = result.drift_report

        # === Proactive ===
        assert result.proactive_times_today == 2
        assert result.proactive_last_contact is not None

        # === Time Context ===
        assert result.time_period is not None
        assert result.time_period in ("morning", "afternoon", "evening", "night", "late_night")
        assert result.time_datetime is not None

        # === User Emotion ===
        assert result.user_emotion == "happy"  # last user message
        assert result.user_emotion_intensity == 0.8

    @pytest.mark.asyncio
    async def test_state_collector_partial(self):
        """Test that collect() works with only some subsystems available."""
        collector = StateCollector(
            mood_engine=None,
            dialogue_thinker=None,
            open_loop_engine=None,
            topic_tracker=None,
            chat_history=None,
            personality_engine=None,
            affection_storage=None,
            identity=None,
            life_summary=None,
            persona_loader=None,
            drift_monitor=None,
            proactive_messenger=None,
        )

        result = await collector.collect("test_user", "girlfriend_001")

        # Type check
        assert isinstance(result, BrainInput)

        # All subsystem-dependent fields should be None
        assert result.mood_type is None
        assert result.mood_valence is None
        assert result.dialogue_thought is None
        assert result.openloop_events is None
        assert result.current_topic is None
        assert result.topic_keywords is None
        assert result.chat_history_summary is None
        assert result.personality_trust is None
        assert result.affection_level is None
        assert result.affection_days_known is None
        assert result.identity_context is None
        assert result.life_summary is None
        assert result.persona_name is None
        assert result.persona_traits is None
        assert result.drift_report is None
        assert result.proactive_times_today is None
        assert result.proactive_last_contact is None
        assert result.user_emotion is None
        assert result.user_emotion_intensity is None

        # Time context should always be available (no subsystem dependency)
        assert result.time_period is not None
        assert result.time_datetime is not None

    @pytest.mark.asyncio
    async def test_state_collector_empty(self):
        """Test that StateCollector with no args at all works."""
        collector = StateCollector()
        result = await collector.collect("test_user")
        assert isinstance(result, BrainInput)
        # Only time context fields should be non-None
        assert result.time_period is not None
        assert result.time_datetime is not None
        assert result.mood_type is None


# =============================================================================
# ThoughtOrganizer tests
# =============================================================================


class TestThoughtOrganizer:
    """ThoughtOrganizer tests"""

    def _make_full_input(self) -> BrainInput:
        """Helper: create a BrainInput with all fields populated."""
        return BrainInput(
            mood_valence=0.8,
            mood_arousal=0.6,
            mood_intensity=0.5,
            openloop_events=["下周面试（待完成）", "项目开发（待完成）"],
            current_topic="工作",
            user_emotion="happy",
            personality_trust=0.7,
            personality_jealousy=0.3,
            affection_level=65.0,
            identity_context=(
                "【用户身份档案】\n"
                "- 教育背景：计算机专业\n"
                "- 兴趣：编程、游戏"
            ),
            life_summary=(
                "【用户长期画像】\n"
                "近期状态：正在找工作\n"
                "当前目标：拿到好的 offer"
            ),
            persona_name="小雨",
            persona_traits=["温柔", "活泼", "粘人"],
            time_period="evening",
            proactive_times_today=2,
        )

    # ────────── Normal ──────────

    def test_thought_organizer_normal(self):
        """正常转换：所有字段非空时，应生成正确的念头列表"""
        bi = self._make_full_input()
        organizer = ThoughtOrganizer()
        thoughts = organizer.organize(bi)

        assert len(thoughts) >= 8, "Should generate thoughts from most fields"

        # 类型检查
        for t in thoughts:
            assert isinstance(t, MonologueThought)
            assert t.source, "source should not be empty"
            assert t.content, "content should not be empty"
            assert 0.0 <= t.priority <= 1.0, f"priority out of range: {t.priority}"
            assert t.category in (
                "feeling", "memory", "intention", "observation", "concern",
            ), f"invalid category: {t.category}"

        # 同一 source 不重复
        sources = [t.source for t in thoughts]
        assert len(sources) == len(set(sources)), f"duplicate sources: {sources}"

        # 按优先级降序排列
        for i in range(len(thoughts) - 1):
            assert (
                thoughts[i].priority >= thoughts[i + 1].priority
            ), f"thoughts not sorted at index {i}: {thoughts[i].priority} < {thoughts[i + 1].priority}"

        # Mood thought（最高优先级）
        mood_thoughts = [t for t in thoughts if t.source == "mood"]
        assert len(mood_thoughts) == 1
        mt = mood_thoughts[0]
        assert mt.category == "feeling"
        assert mt.priority >= 0.8
        # mood_valence=0.8 (>0.5) + arousal=0.6 (>0.5) → excited
        assert "兴奋" in mt.content or "不错" in mt.content

        # Content 是第一人称视角
        assert any(t.content.startswith("我") for t in thoughts)

        # 冲突输入保留（mood=happy + user_emotion=happy → 两条都保留）
        mood_sources = {t.source for t in thoughts}
        assert "mood" in mood_sources
        assert "user_emotion" in mood_sources

    # ────────── Empty ──────────

    def test_thought_organizer_empty(self):
        """空输入应返回默认念头"""
        bi = BrainInput()
        organizer = ThoughtOrganizer()
        thoughts = organizer.organize(bi)

        assert len(thoughts) == 1
        assert thoughts[0].content == "此时我心里很平静。"
        assert thoughts[0].priority == 0.1
        assert thoughts[0].category == "observation"
        assert thoughts[0].source == "brain"

    # ────────── Partial ──────────

    def test_thought_organizer_partial(self):
        """部分字段非空时，只生成对应的念头"""
        bi = BrainInput(
            mood_valence=0.2,  # low → sad
            current_topic="考试",
            user_emotion="sad",
            time_period="late_night",
        )
        organizer = ThoughtOrganizer()
        thoughts = organizer.organize(bi)

        sources = {t.source for t in thoughts}
        assert "mood" in sources
        assert "topic" in sources
        assert "user_emotion" in sources
        assert "time" in sources
        # These should NOT be present
        assert "openloop" not in sources
        assert "identity" not in sources
        assert "life_summary" not in sources
        assert "affection" not in sources
        assert "personality" not in sources

        # 检查 mood 是低落的
        mood = next(t for t in thoughts if t.source == "mood")
        assert "闷" in mood.content

        # 检查 user_emotion 对应 sad → 他好像不太开心……
        ue = next(t for t in thoughts if t.source == "user_emotion")
        assert "不太开心" in ue.content

    # ────────── Truncation ──────────

    def test_thought_organizer_truncation(self):
        """Token 超限时低优先级念头被截断"""
        bi = self._make_full_input()
        # 设置极低的 max_tokens，只允许 1 条念头
        # "我心情不错，感觉有点兴奋" ≈ 13 字符 → 6 tokens
        organizer = ThoughtOrganizer(max_tokens=6)
        thoughts = organizer.organize(bi)

        total_tokens = sum(max(1, len(t.content) // 2) for t in thoughts)
        assert total_tokens <= 6, f"total_tokens={total_tokens} exceeds max_tokens=6"
        assert len(thoughts) >= 1

        # 高优先级念头应被保留（mood thought）
        assert thoughts[0].source == "mood"

    def test_thought_organizer_truncation_keeps_high_priority(self):
        """截断时保留高优先级、移除低优先级"""
        bi = self._make_full_input()
        # 设置 max_tokens 足够容纳 mood + openloop，但不足以容纳全部
        # mood: ~6 tokens, openloop: "我记得他下周面试" → 9 chars → 4 tokens
        # 合计 10 tokens
        # 设置 max_tokens=12 → 应保留 mood + openloop + 部分其他
        organizer = ThoughtOrganizer(max_tokens=12)
        thoughts = organizer.organize(bi)

        total_tokens = sum(max(1, len(t.content) // 2) for t in thoughts)
        assert total_tokens <= 12

        # mood 始终保留（最高优先级）
        assert any(t.source == "mood" for t in thoughts)

        # 没有超过 max_tokens 的单独一条
        for t in thoughts:
            assert max(1, len(t.content) // 2) <= 12

    # ────────── Conflicting ──────────

    def test_thought_organizer_conflicting(self):
        """冲突输入（happy mood + sad user）两条都保留"""
        bi = BrainInput(
            mood_valence=0.9,  # happy
            mood_arousal=0.7,
            user_emotion="sad",  # sad user
        )
        organizer = ThoughtOrganizer()
        thoughts = organizer.organize(bi)

        sources = {t.source for t in thoughts}
        assert "mood" in sources
        assert "user_emotion" in sources

        mood = next(t for t in thoughts if t.source == "mood")
        user = next(t for t in thoughts if t.source == "user_emotion")

        # mood says positive
        assert "不错" in mood.content or "兴奋" in mood.content
        # user emotion says sad → 他好像不太开心……
        assert "不太开心" in user.content


# =============================================================================
# CharacterBreakDetector tests
# =============================================================================


class TestCharacterBreakDetector:
    """CharacterBreakDetector tests"""

    def test_character_break_positive(self):
        """Detect character breaks when AI uses generic AI tone"""
        detector = CharacterBreakDetector(persona_name="小雨", enabled=True)

        # Generic AI tone patterns (confidence 0.9)
        test_cases = [
            ("作为AI，我没有真实情感", "作为AI"),
            ("作为一个AI助手，我", "作为一个AI"),
            ("我是AI语言模型", "我是AI"),
            ("我是人工智能，不能", "我是人工智能"),
            ("我没有情感体验能力", "我没有情感"),
            ("作为语言模型，我无法", "作为语言模型"),
            ("作为大语言模型，我不能", "作为大语言模型"),
            ("作为助手，我可以", "作为助手"),
            ("作为一个助手，我建议", "作为一个助手"),
        ]

        for reply, expected_trigger in test_cases:
            result = detector.check(reply)
            assert result.is_break, f"Should detect break in: {reply}"
            assert result.trigger_phrase == expected_trigger, (
                f"Expected trigger '{expected_trigger}', got '{result.trigger_phrase}'"
            )
            assert result.confidence >= 0.9, (
                f"Expected confidence >= 0.9, got {result.confidence}"
            )

        # Service-oriented tone (confidence 0.7)
        service_cases = [
            ("有什么我可以帮你的吗", "有什么我可以帮你的"),
            ("请问你需要什么帮助", "请问你需要"),
            ("我可以帮你解决这个问题", "我可以帮你"),
            ("我能为你做些什么", "我能为你"),
        ]

        for reply, expected_trigger in service_cases:
            result = detector.check(reply)
            assert result.is_break, f"Should detect break in: {reply}"
            assert result.trigger_phrase == expected_trigger
            assert result.confidence >= 0.7

    def test_character_break_no_false(self):
        """Do NOT fire on normal character-appropriate replies"""
        detector = CharacterBreakDetector(persona_name="小雨", enabled=True)

        safe_replies = [
            "今天天气真好呀，我们去散步吧！",
            "我好想你呀，什么时候来找我玩",
            "你最近在忙什么？好久没见你了",
            "我今天看到一只可爱的小猫，想到了你",
            "晚安啦，做个好梦~",
            "我心情不太好，你能陪陪我吗",
            "你吃饭了吗？要注意身体哦",
            "小雨觉得你今天看起来很开心呢",
            "我想听你讲故事",
            "哈哈你好可爱呀",
        ]

        for reply in safe_replies:
            result = detector.check(reply)
            assert not result.is_break, f"Should NOT detect break in: {reply}"
            assert result.trigger_phrase is None
            assert result.confidence == 0.0

    def test_character_break_user_mention_ai(self):
        """Do NOT fire when user mentioned AI topic first"""
        detector = CharacterBreakDetector(persona_name="小雨", enabled=True)

        # User mentions AI → AI response about AI is acceptable
        user_ai_questions = [
            "你是不是AI",
            "你是机器人吗",
            "你是真人吗",
            "你是AI吗",
            "你到底是谁",
            "你是人工智能吗",
        ]

        for user_msg in user_ai_questions:
            ai_reply = "作为AI，我确实没有人类的情感，但我可以尽力理解你。"
            result = detector.check(ai_reply, user_message=user_msg)
            assert not result.is_break, (
                f"Should NOT fire when user asks '{user_msg}' and AI responds with AI-related content"
            )

        # Without user_ai mention, the same reply SHOULD trigger
        result = detector.check("作为AI，我确实没有人类的情感，但我可以尽力理解你。")
        assert result.is_break, "Without user AI mention, same reply should trigger"

    def test_character_break_disabled(self):
        """When detector is disabled, should never fire"""
        detector = CharacterBreakDetector(persona_name="小雨", enabled=False)

        result = detector.check("作为AI，我是来帮助你的")
        assert not result.is_break
        assert result.trigger_phrase is None
        assert result.confidence == 0.0

        # Even with service patterns
        result = detector.check("有什么我可以帮你的吗")
        assert not result.is_break

    def test_character_break_empty_reply(self):
        """Empty reply should not trigger"""
        detector = CharacterBreakDetector(persona_name="小雨", enabled=True)

        result = detector.check("")
        assert not result.is_break

        result = detector.check("   ")
        assert not result.is_break

    def test_character_break_persona_name_switch(self):
        """Detect when persona name + generic AI pattern appear together"""
        detector = CharacterBreakDetector(persona_name="小雨", enabled=True)

        # Reply mentions persona name AND generic AI pattern → break (AI pattern caught first)
        reply = "小雨是我的角色名，作为AI我其实没有这个名字"
        result = detector.check(reply)
        assert result.is_break
        assert result.confidence >= 0.9

        # Reply mentions a different name (not persona) + AI → should still fire on AI pattern
        reply = "小红做得很好，作为AI我表扬她"
        result = detector.check(reply)
        assert result.is_break
        assert result.trigger_phrase == "作为AI"
        assert result.confidence >= 0.9

    def test_character_break_toggle_enabled(self):
        """Test enabling/disabling at runtime"""
        detector = CharacterBreakDetector(enabled=False)

        result = detector.check("作为AI，我是来帮助你的")
        assert not result.is_break

        detector.enabled = True
        result = detector.check("作为AI，我是来帮助你的")
        assert result.is_break

        detector.enabled = False
        result = detector.check("作为AI，我是来帮助你的")
        assert not result.is_break
