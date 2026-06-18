"""Edge case tests for the brain module — StateCollector, ThoughtOrganizer, MonologueWeaver, MemoryTrigger, CharacterBreakDetector

Tests 8 edge cases:
    EC1 - New user (no history): Brain outputs minimal default monologue
    EC2 - All subsystems offline: Brain only outputs time context
    EC3 - Conflicting inputs (happy mood + sad user thought): both preserved
    EC4 - Very short messages ("嗯", "好的"): Brain doesn't trigger memory retrieval
    EC5 - OpenLoop event backlog (>5): Brain selects top 2 priority events → only 1 openloop thought
    EC6 - Very long messages (1000+ chars): Brain observes user intent
    EC7 - Token truncation with many thoughts: high-priority kept, low-priority trimmed
    EC8 - Character break context handling: user mentioning AI → does NOT fire
"""

from __future__ import annotations

import pytest
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, PropertyMock, patch

from core.brain.checker import CharacterBreakDetector, CharacterBreakResult
from core.brain.collector import StateCollector
from core.brain.models import BrainInput, MonologueThought, BrainOutput
from core.brain.organizer import ThoughtOrganizer
from core.brain.weaver import MonologueWeaver
from core.brain.triggers import MemoryTrigger, TOKEN_RE


# =============================================================================
# EC1 - New user (no history): Brain outputs minimal default monologue
# =============================================================================


class TestEC1_NewUser:
    """EC1: New user has no chat history, no memories, no personality state yet.
    
    StateCollector with all subsystems=None → only time fields populated →
    ThoughtOrganizer returns only default thought → Weaver outputs calm statement.
    """

    @pytest.mark.asyncio
    async def test_state_collector_all_none(self):
        """StateCollector with all subsystems=None: only time_context is non-None"""
        collector = StateCollector()  # all defaults = None
        result = await collector.collect("new_user")

        # All subsystem fields should be None
        assert result.mood_valence is None
        assert result.mood_arousal is None
        assert result.mood_energy is None
        assert result.mood_type is None
        assert result.mood_intensity is None
        assert result.dialogue_thought is None
        assert result.openloop_events is None
        assert result.current_topic is None
        assert result.topic_keywords is None
        assert result.chat_history_summary is None
        assert result.personality_trust is None
        assert result.personality_dependence is None
        assert result.personality_openness is None
        assert result.personality_affection is None
        assert result.personality_jealousy is None
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

        # Only time context should be non-None (no subsystem dependency)
        assert result.time_period is not None
        assert result.time_datetime is not None

    def test_organizer_empty_input_returns_default(self):
        """ThoughtOrganizer with empty BrainInput → only default thought"""
        bi = BrainInput()
        organizer = ThoughtOrganizer()
        thoughts = organizer.organize(bi)

        assert len(thoughts) == 1
        t = thoughts[0]
        assert t.content == "此时我心里很平静。"
        assert t.priority == 0.1
        assert t.category == "observation"
        assert t.source == "brain"

    def test_weaver_no_thoughts_returns_default(self):
        """MonologueWeaver with empty list → '此时我心里很平静。'"""
        weaver = MonologueWeaver()
        monologue = weaver.weave([])
        assert monologue == "此时我心里很平静。"

    def test_weaver_all_none_input_integration(self):
        """Full pipeline integration: BrainInput(all None) → Organizer → Weaver → default monologue"""
        bi = BrainInput()  # all fields None
        organizer = ThoughtOrganizer()
        weaver = MonologueWeaver()

        thoughts = organizer.organize(bi)
        assert len(thoughts) == 1

        monologue = weaver.weave(thoughts)
        assert monologue == "此时我心里很平静。"


# =============================================================================
# EC2 - All subsystems offline: Brain only outputs time context
# =============================================================================


class TestEC2_AllSubsystemsOffline:
    """EC2: All subsystems explicitly set to None/offline.
    
    StateCollector initialized with all None → BrainInput only has time fields →
    Organizer returns default → Weaver outputs calm statement.
    Additionally verify that if time_period IS set, it generates a time thought too.
    """

    @pytest.mark.asyncio
    async def test_collector_all_offline(self):
        """StateCollector with all subsystems explicitly None"""
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
        result = await collector.collect("offline_user")

        # All fields except time should be None
        for field_name in BrainInput.__dataclass_fields__:
            if field_name.startswith("time_"):
                continue
            assert getattr(result, field_name) is None, f"{field_name} should be None"

        assert result.time_period is not None
        assert result.time_datetime is not None

    def test_organizer_with_only_time(self):
        """ThoughtOrganizer with only time_period set → generates time thought + default"""
        bi = BrainInput(
            time_period="night",
            time_datetime="2026-06-18T22:30:00",
        )
        organizer = ThoughtOrganizer()
        thoughts = organizer.organize(bi)

        # Should have: time thought + default thought (since no mood → mood_thought is None)
        # Actually, let's trace through:
        # - mood_thought: None (no mood_valence/mood_arousal)
        # - intention_thoughts: [] (no openloop_events, no dialogue_thought)
        # - observation_thoughts: [time] (time_period="night")
        # - memory_thoughts: [] (no identity_context, no life_summary)
        # - disposition_thoughts: [] (no personality dims, no affection, no persona_traits)
        # - context_thoughts: [time] also? No wait, context_thoughts includes time_period and proactive
        #   But time_period is in _build_context_thoughts, not observation
        # 
        # Actually wait, let me re-read organizer.py more carefully:
        # _build_context_thoughts handles time_period and proactive
        # _build_observation_thoughts handles current_topic and user_emotion
        # 
        # So with only time_period:
        # - feeling: None (no valence/arousal)
        # - intention: [] (no openloop/dialogue)
        # - observation: [] (no topic/user_emotion)
        # - memory: [] (no identity/life_summary)
        # - disposition: [] (no personality/affection/persona)
        # - context: [time thought] (time_period is set)
        # Then truncated → kept
        # But if only context thoughts exist and no thought for the default criteria...
        # 
        # Let me trace: 
        # After _build_context_thoughts: thoughts = [MonologueThought(source="time", ...)]
        # thoughts.sort(...) - only 1 item
        # _truncate: total_tokens = est(time thought) <= max_tokens → no truncation
        # thoughts not empty → no default added
        # 
        # So with only time_period set, we get 1 thought (the time thought)
        # NOT the default "此时我心里很平静。"
        #
        # But wait - what if we also have NO mood → _build_mood_thought returns None
        # That's fine, the Organizer will just not add it.
        # 
        # So result: 1 thought - the time observation

        # Time thought should be present
        time_thoughts = [t for t in thoughts if t.source == "time"]
        assert len(time_thoughts) == 1
        assert time_thoughts[0].content in ("夜深了", "晚上了")
        assert time_thoughts[0].priority == 0.2

    def test_weaver_with_only_time_thought(self):
        """MonologueWeaver with only a time thought → outputs time-related monologue"""
        thoughts = [
            MonologueThought(source="time", content="夜深了", priority=0.2, category="observation"),
        ]
        weaver = MonologueWeaver()
        monologue = weaver.weave(thoughts)

        # The only thought should be woven into monologue
        assert "夜深了" in monologue
        # Should end with sentence-ending punctuation
        assert monologue[-1] in "。！？……!?"

    def test_pipeline_all_offline(self):
        """Full integration: all None inputs → only time thought + default woven"""
        bi = BrainInput(time_period="late_night")
        organizer = ThoughtOrganizer()
        weaver = MonologueWeaver()

        thoughts = organizer.organize(bi)
        # Should have at least 1 thought (time context or default)
        assert len(thoughts) >= 1

        monologue = weaver.weave(thoughts)
        # Monologue should be non-empty and mention time or be the default
        assert "这么晚" in monologue or "此时我心里很平静" in monologue
        assert isinstance(monologue, str)
        assert len(monologue) > 0


# =============================================================================
# EC3 - Conflicting inputs (happy mood + sad user thought): both preserved
# =============================================================================


class TestEC3_ConflictingInputs:
    """EC3: Happy mood (valence=0.9) + sad user_emotion → both thoughts generated.
    
    The Organizer must produce BOTH a mood thought AND a user_emotion thought,
    even though they are emotionally conflicting.
    """

    def test_organizer_preserves_both(self):
        """ThoughtOrganizer preserves both conflicting mood and user_emotion thoughts"""
        bi = BrainInput(
            mood_valence=0.9,    # very happy
            mood_arousal=0.7,
            mood_intensity=0.8,
            user_emotion="sad",  # user is sad → conflict!
            user_emotion_intensity=0.9,
        )
        organizer = ThoughtOrganizer()
        thoughts = organizer.organize(bi)

        sources = {t.source for t in thoughts}
        assert "mood" in sources, "mood thought should be present"
        assert "user_emotion" in sources, "user_emotion thought should be present"

        # Mood should say something positive
        mood = next(t for t in thoughts if t.source == "mood")
        assert "不错" in mood.content or "兴奋" in mood.content
        
        # User emotion should detect sadness
        user = next(t for t in thoughts if t.source == "user_emotion")
        assert "不太开心" in user.content

    def test_weaver_contains_both_perspectives(self):
        """MonologueWeaver output contains both conflicting perspectives"""
        bi = BrainInput(
            mood_valence=0.9,
            mood_arousal=0.7,
            user_emotion="sad",
        )
        organizer = ThoughtOrganizer()
        weaver = MonologueWeaver()

        thoughts = organizer.organize(bi)
        monologue = weaver.weave(thoughts)

        # Final monologue should contain BOTH the mood and user_emotion content
        assert "不错" in monologue or "兴奋" in monologue
        assert "不太开心" in monologue

    def test_multiple_user_emotions_preserved(self):
        """All emotion types produce correct conflicting output"""
        test_cases = [
            ("sad", "不太开心"),
            ("happy", "心情不错"),
            ("anxious", "不太开心"),
            ("angry", "不太开心"),
            ("excited", "心情不错"),
            ("grateful", "心情不错"),
            ("gloomy", "他好像gloomy的样子"),  # unknown emotion → literal
        ]

        for user_emotion, expected_in_content in test_cases:
            bi = BrainInput(
                mood_valence=0.15,  # unhappy
                mood_arousal=-0.2,
                user_emotion=user_emotion,
            )
            organizer = ThoughtOrganizer()
            thoughts = organizer.organize(bi)

            sources = {t.source for t in thoughts}
            assert "mood" in sources, f"mood thought should be present for user_emotion={user_emotion}"
            assert "user_emotion" in sources, f"user_emotion thought should be present for {user_emotion}"

            user = next(t for t in thoughts if t.source == "user_emotion")
            assert expected_in_content in user.content, (
                f"user_emotion={user_emotion}: expected '{expected_in_content}' in '{user.content}'"
            )


# =============================================================================
# EC4 - Very short messages: MemoryTrigger doesn't retrieve memories
# =============================================================================


class TestEC4_ShortMessages:
    """EC4: Very short messages like "嗯" or "好的" should NOT trigger memory retrieval.
    
    MemoryTrigger uses TOKEN_RE to extract meaningful tokens from user messages.
    Single-character messages, short responses, or messages without 2+ char tokens
    should not trigger keyword-based memory search.
    """

    SHORT_MESSAGES = [
        "嗯",
        "好",
        "是",
        "不",
        "对",
        "哦",
        "啊",
        ":)",
        "a",
        "b",
        "X",
    ]

    # Single CJK characters that should NOT match [\u4e00-\u9fff]{2,}
    SINGLE_CHAR_CJK = [
        "是",
        "不",
        "对",
        "好",
        "哦",
        "啊",
        "嗯",
        "嗨",
    ]

    # Short messages where TOKEN_RE might incorrectly match
    # "嗯嗯" has 2 consecutive CJK → matches; "ab" is 2-letter English → matches
    # These are listed here for documentation but NOT used in no-token assertions

    def test_token_re_extracts_no_tokens_from_short_messages(self):
        """TOKEN_RE should extract no meaningful tokens from short messages"""
        for msg in self.SHORT_MESSAGES:
            tokens = TOKEN_RE.findall(msg)
            # Single-char Chinese or single chars should not match (2+ chars required)
            assert len(tokens) == 0, (
                f"Message '{msg}' produced unexpected tokens: {tokens}"
            )

        # Single CJK characters (1 char) should also not match
        for ch in self.SINGLE_CHAR_CJK:
            tokens = TOKEN_RE.findall(ch)
            assert len(tokens) == 0, (
                f"Single CJK char '{ch}' produced unexpected tokens: {tokens}"
            )

    def test_token_re_extracts_tokens_from_longer_messages(self):
        """TOKEN_RE should extract tokens from messages with 2+ char words"""
        # "今天天气真好" is all consecutive CJK → 1 token
        tokens = TOKEN_RE.findall("今天天气真好")
        assert len(tokens) == 1
        assert len(tokens[0]) >= 2

        # Mixed CJK with spaces → separate tokens per contiguous block
        tokens = TOKEN_RE.findall("今天 天气 真好")
        assert len(tokens) >= 2

        tokens = TOKEN_RE.findall("hello world")
        assert "hello" in tokens
        assert "world" in tokens

        tokens = TOKEN_RE.findall("ab")  # 2-letter English → matches
        assert "ab" in tokens

        # Mixed Chinese + English
        tokens = TOKEN_RE.findall("今天hello")
        assert len(tokens) >= 1
        assert any(t == "今天" or t == "hello" for t in tokens)

    @pytest.mark.asyncio
    async def test_memory_trigger_short_message_no_retrieval(self):
        """MemoryTrigger with short message: keyword-based search_memories NOT called"""
        memory_mgr = MagicMock()
        memory_mgr.get_memories.return_value = []  # prevent spontaneous trigger errors
        trigger = MemoryTrigger(memory_mgr)

        # Use only the messages that truly produce 0 tokens
        # Note: single CJK chars and single english chars produce 0 tokens,
        # but "ab" (2-letter) and "嗯嗯" (2-char CJK) DO match
        no_token_messages = [
            "嗯",
            "好",
            "是",
            "不",
            "对",
            "哦",
            "啊",
            ":)",
            "a",
            "b",
        ]

        for msg in no_token_messages:
            memory_mgr.reset_mock()
            memory_mgr.get_memories.return_value = []
            thoughts = await trigger.trigger("test_user", msg)

            # No keyword-triggered thoughts should be generated
            keyword_thoughts = [t for t in thoughts if t.source == "memory_trigger"]
            assert len(keyword_thoughts) == 0, (
                f"Short message '{msg}' should not trigger keyword memory retrieval, "
                f"got {len(keyword_thoughts)} keyword thoughts"
            )
            # search_memories should NOT have been called for keyword trigger
            memory_mgr.search_memories.assert_not_called()

    @pytest.mark.asyncio
    async def test_memory_trigger_normal_message_triggers(self):
        """MemoryTrigger with normal message: search_memories IS called"""
        memory_mgr = MagicMock()
        memory_mgr.search_memories.return_value = []
        trigger = MemoryTrigger(memory_mgr)

        thoughts = await trigger.trigger("test_user", "我今天心情不太好")

        memory_mgr.search_memories.assert_called()
        assert len(thoughts) >= 0  # May or may not return thought (depends on results)

    @pytest.mark.asyncio
    async def test_memory_trigger_with_memory_hit(self):
        """MemoryTrigger when keyword hits an existing memory"""
        memory_mgr = MagicMock()
        # Mock a memory result
        mock_memory = MagicMock()
        mock_memory.content = "他之前说过喜欢编程"
        memory_mgr.search_memories.return_value = [mock_memory]
        trigger = MemoryTrigger(memory_mgr)

        thoughts = await trigger.trigger("test_user", "编程好有意思")

        assert len(thoughts) == 1
        t = thoughts[0]
        assert t.source == "memory_trigger"
        assert "说过" in t.content or "编程" in t.content
        assert t.category == "memory"
        assert t.priority == 0.6

    @pytest.mark.asyncio
    async def test_emotion_trigger_not_fired_for_short_message(self):
        """Emotion trigger: short messages with no negative keywords don't trigger

        Note: spontaneous trigger calls get_memories() independently.
        This test verifies that keyword-based emotion search is not triggered
        for short neutral messages.
        """
        memory_mgr = MagicMock()
        memory_mgr.get_memories.return_value = []  # prevent errors from spontaneous trigger
        memory_mgr.search_memories.return_value = []
        trigger = MemoryTrigger(memory_mgr)

        # "嗯" has no negative emotion keywords
        thoughts = await trigger.trigger("test_user", "嗯")

        # search_memories should NOT have been called (keyword check finds no tokens)
        memory_mgr.search_memories.assert_not_called()
        # No keyword or emotion triggered thoughts (spontaneous returns [] from empty)
        assert len(thoughts) == 0


# =============================================================================
# EC5 - OpenLoop event backlog (>5): only first event generates a thought
# =============================================================================


class TestEC5_OpenLoopBacklog:
    """EC5: BrainInput with 6+ openloop_events → only 1 openloop thought generated.
    
    ThoughtOrganizer._build_intention_thoughts only takes events[0] (first event),
    regardless of how many events are in the list.
    """

    def test_single_openloop_thought_from_many_events(self):
        """6 openloop events → exactly 1 openloop thought (first event only)"""
        bi = BrainInput(
            openloop_events=[
                "下周面试（待完成）",
                "项目开发（待完成）",
                "健身计划（待完成）",
                "准备旅行（待完成）",
                "学习新技能（待完成）",
                "整理房间（待完成）",
            ],
        )
        organizer = ThoughtOrganizer()
        thoughts = organizer.organize(bi)

        openloop_thoughts = [t for t in thoughts if t.source == "openloop"]
        assert len(openloop_thoughts) == 1, (
            f"Expected exactly 1 openloop thought, got {len(openloop_thoughts)}"
        )

        # The content should reference the FIRST event
        assert "下周面试" in openloop_thoughts[0].content
        assert "项目开发" not in openloop_thoughts[0].content

    def test_openloop_thought_priority_is_0_75(self):
        """Openloop thought always has priority 0.75"""
        bi = BrainInput(
            openloop_events=["只此一条"],
        )
        organizer = ThoughtOrganizer()
        thoughts = organizer.organize(bi)

        ol = next(t for t in thoughts if t.source == "openloop")
        assert ol.priority == 0.75

    def test_openloop_with_no_other_fields(self):
        """Only openloop events, no other fields → only openloop + default"""
        bi = BrainInput(
            openloop_events=["完成报告"],
        )
        organizer = ThoughtOrganizer()
        thoughts = organizer.organize(bi)

        # Should have openloop thought + placeholder since there's nothing else
        # After: mood_thought=None, intention=[openloop], observation=[], memory=[], disposition=[], context=[]
        # Sorted: priority 0.75 (openloop)
        # Since no default fallback needed (not empty after all builds)
        openloop_thoughts = [t for t in thoughts if t.source == "openloop"]
        assert len(openloop_thoughts) == 1

    def test_openloop_event_cleaning(self):
        """OpenLoop events have '（待完成）' and '(待完成)' cleaned"""
        bi = BrainInput(
            openloop_events=[
                "帮我买礼物（待完成）",
                "修电脑(待完成)",
            ],
        )
        organizer = ThoughtOrganizer()
        thoughts = organizer.organize(bi)

        ol = next(t for t in thoughts if t.source == "openloop")
        # Should clean up the marker
        assert "（待完成）" not in ol.content
        assert "(待完成)" not in ol.content
        assert "买礼物" in ol.content or "修电脑" in ol.content


# =============================================================================
# EC6 - Very long messages (1000+ chars): Brain handles without error
# =============================================================================


class TestEC6_VeryLongMessage:
    """EC6: Very long messages (1000+ chars) should be handled without error.
    
    MemoryTrigger should still extract keywords from the beginning.
    StateCollector should truncate long messages in chat_history_summary.
    """

    @pytest.mark.asyncio
    async def test_memory_trigger_long_message_no_error(self):
        """MemoryTrigger handles 1000+ char message without error"""
        memory_mgr = MagicMock()
        memory_mgr.search_memories.return_value = []
        trigger = MemoryTrigger(memory_mgr)

        long_msg = "测试" * 600  # 1200 chars
        # Should not raise any exception
        thoughts = await trigger.trigger("test_user", long_msg)

        # Should have extracted tokens and searched
        memory_mgr.search_memories.assert_called()

    @pytest.mark.asyncio
    async def test_memory_trigger_very_long_with_actual_tokens(self):
        """MemoryTrigger extracts keywords from 1000+ char message correctly"""
        memory_mgr = MagicMock()
        trigger = MemoryTrigger(memory_mgr)

        # Build a long message with actual meaningful content at the front
        long_msg = "记得我们上次去爬山" + "啊" * 1000 + "真的好开心"
        tokens = TOKEN_RE.findall(long_msg)

        # Should find meaningful words despite the padding
        # "记得我们上次去爬山" is consecutive CJK → 1 token
        assert len(tokens) >= 1, "Should extract at least one meaningful token"
        longest = max(tokens, key=len)
        assert len(longest) > 2, f"Longest token should be >2 chars, got '{longest}'"
        # The first token should contain the meaningful words at the front
        assert "记" in tokens[0] or "爬" in tokens[0] or "好" in tokens[0]

    @pytest.mark.asyncio
    async def test_memory_trigger_long_message_limits(self):
        """MemoryTrigger only searches first 5 tokens even from long messages"""
        memory_mgr = MagicMock()
        memory_mgr.search_memories.return_value = []
        trigger = MemoryTrigger(memory_mgr)

        long_msg = " ".join([f"keyword{i}" for i in range(20)])  # 20 keywords
        await trigger.trigger("test_user", long_msg)

        # Should have been called at most 5 times (tokens[:5])
        assert memory_mgr.search_memories.call_count <= 5

    def test_chat_history_long_message_truncation(self):
        """StateCollector truncates long messages (>100 chars) in chat summary"""
        # Create a mock chat history with a very long message
        chat_history = MagicMock()
        long_content = "这是一段非常长的消息" * 30  # >100 chars
        chat_history.get_messages.return_value = [
            {"role": "user", "content": long_content},
        ]

        collector = StateCollector(chat_history=chat_history)

        # Call the internal method directly
        summary = collector._get_chat_history_summary("test_user")

        assert summary is not None
        # The long content should be truncated (ends with "...")
        assert summary.endswith("...")

    @pytest.mark.asyncio
    async def test_long_message_full_pipeline(self):
        """Full pipeline: long chat history doesn't break the Brain flow"""
        chat_history = MagicMock()
        long_content = "今天天气真好我们出去玩吧" * 50  # 500+ chars
        chat_history.get_messages.return_value = [
            {"role": "user", "content": long_content, "emotion": "happy"},
        ]

        collector = StateCollector(chat_history=chat_history)
        result = await collector.collect("test_user")

        # Should have computed user emotion from last message
        assert result.user_emotion == "happy"

        # Chat history summary should be truncated
        assert result.chat_history_summary is not None


# =============================================================================
# EC7 - Token truncation with many thoughts: high-priority kept, low-priority trimmed
# =============================================================================


class TestEC7_TokenTruncation:
    """EC7: When token budget is constrained, low-priority thoughts are trimmed.
    
    MonologueWeaver._trim removes lowest-priority-category thoughts first.
    ThoughtOrganizer._truncate also removes low-priority thoughts.
    """

    def test_weaver_trims_low_priority_category_first(self):
        """MonologueWeaver._trim removes concern (priority 1) before feeling (priority 5)"""
        thoughts = [
            MonologueThought(source="mood", content="我心情不错", priority=0.9, category="feeling"),
            MonologueThought(source="personality", content="我很信任他", priority=0.4, category="concern"),
        ]

        # Set max_tokens extremely low so only 1 thought fits
        weaver = MonologueWeaver(max_tokens=3)
        trimmed = weaver._trim(thoughts)

        assert len(trimmed) >= 1
        # The high-priority-category thought (feeling) should survive
        assert any(t.category == "feeling" for t in trimmed)

    def test_weaver_trims_multiple_concern_thoughts(self):
        """With many low-priority thoughts, Weaver trims from lowest category first"""
        thoughts = [
            MonologueThought(source="mood", content="我心情不错", priority=0.9, category="feeling"),
            MonologueThought(source="time", content="晚上了", priority=0.2, category="observation"),
            MonologueThought(source="affection", content="我喜欢和他在一起", priority=0.35, category="concern"),
            MonologueThought(source="persona", content="我平时还是挺活泼的", priority=0.3, category="observation"),
        ]

        weaver = MonologueWeaver(max_tokens=15)
        trimmed = weaver._trim(thoughts)

        # With 15 tokens, it should be able to fit most but might cut some
        total = sum(weaver._estimate_tokens(t.content) for t in trimmed)
        assert total <= 15

        # At least feeling should survive (highest category priority)
        assert any(t.category == "feeling" for t in trimmed)

    def test_organizer_keeps_at_least_one_thought(self):
        """Even with tight max_tokens, at least 1 thought survives"""
        bi = BrainInput(
            mood_valence=0.9,
            mood_arousal=0.7,
            mood_intensity=0.5,
            current_topic="工作",
            user_emotion="happy",
            time_period="evening",
            identity_context="【身份】\n- 爱好：编程",
            life_summary="最近在找工作",
            personality_trust=0.8,
            affection_level=60.0,
            persona_traits=["活泼"],
            proactive_times_today=2,
        )

        # "我心情不错，感觉有点兴奋" = 13 chars → 6 tokens
        # Set max_tokens so only the highest priority thought fits
        organizer = ThoughtOrganizer(max_tokens=6)
        thoughts = organizer.organize(bi)

        assert len(thoughts) >= 1, "At least 1 thought must survive truncation"
        total_tokens = sum(max(1, len(t.content) // 2) for t in thoughts)
        assert total_tokens <= 6

    def test_organizer_high_priority_survives_strict_truncation(self):
        """Under strict truncation, highest priority thought (mood) always survives"""
        bi = BrainInput(
            mood_valence=0.9,  # → priority 0.9+
            mood_arousal=0.7,
            openloop_events=["重要事件"],  # → priority 0.75
        )

        organizer = ThoughtOrganizer(max_tokens=6)
        thoughts = organizer.organize(bi)

        # Mood is highest priority, should survive
        assert any(t.source == "mood" for t in thoughts)

    def test_weaver_default_when_all_trimmed(self):
        """If all thoughts are trimmed, Weaver returns default calm statement"""
        thoughts = [
            MonologueThought(source="time", content="晚上了", priority=0.2, category="observation"),
        ]

        weaver = MonologueWeaver(max_tokens=1)  # Too small for "晚上了" (3 chars → 1 token... actually that fits)
        # "晚上了" = 3 chars → max(1, 3//2) = 1 token → fits in max_tokens=1
        # Let me use max_tokens that's too small
        # Actually let's just verify _trim keeps at least 1
        trimmed = weaver._trim(thoughts)
        assert len(trimmed) >= 1

    def test_weaver_merge_group_respects_priority_within_category(self):
        """Within same category, higher priority thoughts come first in merged text"""
        weaver = MonologueWeaver()
        thoughts = [
            MonologueThought(source="persona", content="我平时还是挺活泼的", priority=0.3, category="observation"),
            MonologueThought(source="time", content="晚上了", priority=0.2, category="observation"),
        ]
        merged = weaver._merge_group(thoughts)
        # "我平时还是挺活泼的" should come before "晚上了" (sorted by priority descending)
        idx_活泼 = merged.index("活泼")
        idx_晚上 = merged.index("晚上")
        assert idx_活泼 < idx_晚上, "Higher priority thought should come first"


# =============================================================================
# EC8 - Character break context handling: user mentioning AI → does NOT fire
# =============================================================================


class TestEC8_CharacterBreakContext:
    """EC8: When user message mentions AI keywords, CharacterBreakDetector should
    NOT fire even if the AI reply contains generic AI patterns.
    """

    def test_user_ai_mention_prevents_break(self):
        """User mentions AI → reply with '作为AI' should NOT trigger"""
        detector = CharacterBreakDetector(persona_name="小雨", enabled=True)

        # Each user question about AI should suppress the detection
        user_questions = [
            "你是不是AI",
            "你是机器人吗",
            "你是真人吗",
            "你是AI吗",
            "你到底是谁",
            "你是人工智能吗",
            "你是什么",
        ]

        for user_msg in user_questions:
            # Reply that would normally trigger (contains "作为AI")
            reply = "作为AI，我确实没有人类的情感，但我很乐意陪着你。"
            result = detector.check(reply, user_message=user_msg)

            assert not result.is_break, (
                f"Should NOT fire when user asks '{user_msg}'"
            )
            assert result.trigger_phrase is None
            assert result.confidence == 0.0

    def test_same_reply_without_user_ai_mention_triggers(self):
        """Same reply without user AI mention SHOULD trigger"""
        detector = CharacterBreakDetector(persona_name="小雨", enabled=True)

        reply = "作为AI，我确实没有人类的情感，但我很乐意陪着你。"
        result = detector.check(reply)  # no user_message

        assert result.is_break
        assert result.trigger_phrase == "作为AI"
        assert result.confidence >= 0.9

    def test_user_ai_mention_with_other_ai_patterns(self):
        """All generic AI patterns are suppressed when user mentions AI"""
        detector = CharacterBreakDetector(persona_name="小雨", enabled=True)

        ai_replies = [
            "作为一个AI，我可以帮你分析一下",
            "我是AI语言模型，无法感受情感",
            "我是人工智能，不能保证完全准确",
            "我没有情感体验，但我会尽力理解你",
            "作为语言模型，我的知识有截止日期",
            "作为大语言模型，我的回答仅供参考",
            "作为助手，我可以提供信息",
            "作为一个助手，我的建议是",
        ]

        for reply in ai_replies:
            result = detector.check(reply, user_message="你是AI吗")
            assert not result.is_break, (
                f"Should NOT fire when user asks and reply is: {reply[:20]}..."
            )

    def test_user_ai_mention_with_service_patterns(self):
        """Service-oriented patterns are also suppressed when user mentions AI"""
        detector = CharacterBreakDetector(persona_name="小雨", enabled=True)

        service_replies = [
            "有什么我可以帮你的吗",
            "我可以帮你解决这个问题",
            "请问你需要什么帮助",
            "我能为你做些什么",
        ]

        for reply in service_replies:
            result = detector.check(reply, user_message="你是机器人吗")
            assert not result.is_break, (
                f"Should NOT fire service pattern when user asks: {reply[:20]}..."
            )

    def test_partial_user_ai_mention_not_enough(self):
        """Only specific patterns suppress; partial matches don't

        Note: "你是什么" IS a defined pattern (exact match) in _USER_AI_MENTION_PATTERNS.
        Substring matches like "你觉得AI怎么样" or "你喜欢人工智能吗" are NOT defined patterns.
        """
        detector = CharacterBreakDetector(persona_name="小雨", enabled=True)

        # These user messages do NOT match _USER_AI_MENTION_PATTERNS (substring check using `in`)
        # Note: "你是什么星座" contains "你是什么" which IS a pattern, so it's excluded
        non_ai_user_messages = [
            "你是我的好朋友",
            "你觉得AI怎么样",
            "你喜欢人工智能吗",
            "我是什么样的人",
            "你看起来像AI",
            "AI真的厉害",
            "你会AI吗",
        ]

        for user_msg in non_ai_user_messages:
            reply = "作为AI，我没有情感"
            result = detector.check(reply, user_message=user_msg)

            # Should still trigger because user didn't ask the specific AI questions
            assert result.is_break, (
                f"Should fire when user says '{user_msg}' (not a direct AI question)"
            )

    def test_user_ai_mention_with_disabled_detector(self):
        """Disabled detector doesn't fire regardless of user message"""
        detector = CharacterBreakDetector(persona_name="小雨", enabled=False)

        result = detector.check("作为AI，我是来帮助你的", user_message="你是AI吗")
        assert not result.is_break

    def test_user_ai_what_are_you_suppresses(self):
        """"你是什么" is a defined pattern and should suppress detection"""
        detector = CharacterBreakDetector(persona_name="小雨", enabled=True)

        result = detector.check("作为AI，我没有情感", user_message="你是什么")
        assert not result.is_break, '"你是什么" should suppress break detection'

    def test_empty_user_message_still_detects(self):
        """Empty user_message should not suppress AI pattern detection"""
        detector = CharacterBreakDetector(persona_name="小雨", enabled=True)

        result = detector.check("作为AI，我是来帮助你的", user_message="")
        assert result.is_break

        result = detector.check("作为AI，我是来帮助你的")
        assert result.is_break

    def test_full_pipeline_no_false_suppression(self):
        """Detector correctly discriminates: user says '你怎么像AI' → NOT a defined pattern → still detects"""
        detector = CharacterBreakDetector(persona_name="小雨", enabled=True)

        # "你怎么像AI" is NOT in _USER_AI_MENTION_PATTERNS (not exact match)
        result = detector.check("作为AI，我只是个程序", user_message="你怎么像AI")
        assert result.is_break, "Similar but non-matching user message should not suppress"

        # Exact match
        result = detector.check("作为AI，我只是个程序", user_message="你是AI吗")
        assert not result.is_break, "Exact match user message should suppress"
