"""Focused tests for compact model-facing brain state."""

from core.brain.models import BrainInput, MonologueThought
from core.brain.runtime_context import RuntimeStateFormatter


def _thought(source: str, content: str, category: str = "observation") -> MonologueThought:
    return MonologueThought(
        source=source,
        content=content,
        priority=0.8,
        category=category,
    )


def test_neutral_generic_state_is_not_injected() -> None:
    formatter = RuntimeStateFormatter()
    brain_input = BrainInput(
        mood_type="neutral",
        affection_level=50,
        time_period="afternoon",
        persona_traits=["活泼"],
    )
    thoughts = [
        _thought("mood", "我心情还算平静", "feeling"),
        _thought("affection", "我和他相处得还不错", "concern"),
        _thought("time", "下午了"),
        _thought("persona", "我平时还是挺活泼的"),
    ]

    assert formatter.format(brain_input, thoughts) == ""


def test_meaningful_state_is_grouped_for_the_reply_model() -> None:
    formatter = RuntimeStateFormatter()
    brain_input = BrainInput(
        mood_type="sad",
        affection_level=72,
        time_period="late_night",
    )
    thoughts = [
        _thought("mood", "我心里有点闷，不太想说话", "feeling"),
        _thought("openloop", "我记得他明天还要练车", "intention"),
        _thought("user_emotion", "他好像不太开心"),
        _thought("memory_trigger", "他之前说过练车时有些紧张", "memory"),
        _thought("affection", "我感觉跟他越来越亲近了", "concern"),
        _thought("time", "这么晚了他还没睡"),
    ]

    context = formatter.format(brain_input, thoughts)

    assert context.startswith("【本轮运行时心境】")
    assert "心境：" in context
    assert "本轮关注：" in context
    assert "关联记忆：" in context
    assert "关系倾向：" in context
    assert "环境：" in context
    assert "此时我心里很平静" not in context


def test_runtime_context_never_exceeds_configured_budget() -> None:
    formatter = RuntimeStateFormatter(max_tokens=80)
    brain_input = BrainInput(
        mood_type="angry",
        affection_level=90,
        time_period="late_night",
    )
    long_text = "这是一段很长但有意义的状态" * 30
    thoughts = [
        _thought("mood", long_text, "feeling"),
        _thought("openloop", long_text, "intention"),
        _thought("memory_trigger", long_text, "memory"),
        _thought("affection", long_text, "concern"),
        _thought("time", long_text),
    ]

    context = formatter.format(brain_input, thoughts)

    assert len(context) // 2 <= 80
