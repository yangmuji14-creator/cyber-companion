from core.emotion.mood import MoodState, MoodType
from core.persona import Persona, build_fused_style


def test_low_mood_preserves_persona_baseline():
    persona = Persona(id="p", name="测试", personality=["元气", "爱开玩笑"])
    mood = MoodState(mood=MoodType.SAD, intensity=0.8, energy=0.2)
    prompt = build_fused_style(persona, mood, "回复略微低落")
    assert "元气、爱开玩笑" in prompt
    assert "不能改变人格" in prompt
    assert "更安静" in prompt
    assert "精力较低" in prompt


def test_high_mood_respects_calm_persona():
    persona = Persona(id="p", name="测试", personality=["沉稳", "克制"])
    mood = MoodState(mood=MoodType.EXCITED, intensity=0.9)
    prompt = build_fused_style(persona, mood)
    assert "沉稳人设应克制" in prompt
