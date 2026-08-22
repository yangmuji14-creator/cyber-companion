"""First-person diary generation is separate from reply-time state."""

import json
from types import SimpleNamespace

import pytest

from core.llm.base import LLMResponse
from core.memory.life_summary import LifeSummaryEngine


class FakeLLM:
    def __init__(self, payload: dict | None = None, error: Exception | None = None):
        self.payload = payload
        self.error = error
        self.calls = []

    async def chat(self, messages, system_prompt=None, **kwargs):
        self.calls.append({
            "messages": messages,
            "system_prompt": system_prompt,
            "kwargs": kwargs,
        })
        if self.error:
            raise self.error
        return LLMResponse(
            content=json.dumps(self.payload, ensure_ascii=False),
            model="test-model",
        )


class FakePersonaLoader:
    @staticmethod
    def get(_persona_id):
        return SimpleNamespace(
            name="小可爱",
            personality=["温柔", "活泼", "偶尔傲娇"],
            background="正在学习如何更认真地理解对方。",
            nickname_for_user="",
        )


@pytest.mark.asyncio
async def test_diary_is_first_person_persisted_and_not_reused_as_hidden_reasoning(tmp_path) -> None:
    llm = FakeLLM({
        "diary": "今天他说起练车时，我嘴上装作不在意，后来却一直想着他会不会紧张。\n\n我好像越来越习惯等他的消息了。",
        "recent_status": "惦记他的练车进展",
        "emotional_trend": "平静里带一点牵挂",
        "relationship_change": "开始更自然地关心他",
        "key_events": ["他开始练车"],
    })
    engine = LifeSummaryEngine(tmp_path)
    engine.configure_diary_generation(
        llm=llm,
        persona_loader=FakePersonaLoader(),
    )

    diary = await engine.generate_diary(
        user_id="[user_id]",
        persona_id="[persona_id]",
        conversation_count=10,
        memories=["他今天下午去练车了"],
        recent_messages=[{"role": "user", "content": "我下午去练车了"}],
        relationship_level=56,
    )

    assert diary is not None
    assert diary.summary_type == "diary"
    assert "我" in diary.summary
    assert "用户" not in diary.summary
    assert engine.get_latest("[user_id]").summary == diary.summary
    runtime_context = engine.get_context("[user_id]")
    assert diary.summary not in runtime_context
    assert "惦记他的练车进展" in runtime_context
    assert len(llm.calls) == 1
    assert llm.calls[0]["kwargs"]["max_tokens"] == 900


@pytest.mark.asyncio
async def test_same_interaction_checkpoint_does_not_create_duplicate_diary(tmp_path) -> None:
    llm = FakeLLM({
        "diary": "今天我记住了一件很小的事情。越是这样普通的瞬间，我越觉得不想让它轻易过去。",
        "recent_status": "平静",
        "emotional_trend": "稳定",
        "relationship_change": "",
        "key_events": [],
    })
    engine = LifeSummaryEngine(tmp_path)
    engine.configure_diary_generation(llm=llm, persona_loader=FakePersonaLoader())

    first = await engine.generate_diary(
        "[user_id]", "[persona_id]", 10, ["一件小事"], [], 50,
    )
    second = await engine.generate_diary(
        "[user_id]", "[persona_id]", 10, ["一件小事"], [], 50,
    )

    assert first is not None and second is not None
    assert first.id == second.id
    assert engine._sqlite_storage.count_by_user("[user_id]") == 1
    assert len(llm.calls) == 1


@pytest.mark.asyncio
async def test_diary_has_readable_first_person_fallback_when_model_fails(tmp_path) -> None:
    engine = LifeSummaryEngine(tmp_path)
    engine.configure_diary_generation(
        llm=FakeLLM(error=RuntimeError("provider unavailable")),
        persona_loader=FakePersonaLoader(),
    )

    diary = await engine.generate_diary(
        user_id="[user_id]",
        persona_id="[persona_id]",
        conversation_count=10,
        memories=["他说最近在准备考试"],
        recent_messages=[],
        relationship_level=50,
    )

    assert diary is not None
    assert diary.summary_type == "diary"
    assert diary.summary.startswith("今天我")
    assert "想替我们好好记住" in diary.summary
