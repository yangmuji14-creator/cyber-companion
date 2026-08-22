"""Fuse persistent mood with persona without allowing personality drift."""

from __future__ import annotations

from core.emotion.mood import MoodState, MoodType
from core.persona.models import Persona


_LOW_MOODS = {MoodType.TIRED, MoodType.SAD, MoodType.DEPRESSED, MoodType.LONELY}
_HIGH_MOODS = {MoodType.ECSTATIC, MoodType.EXCITED, MoodType.ANGRY, MoodType.ANXIOUS}


def build_fused_style(persona: Persona, mood: MoodState, mood_hint: str = "") -> str:
    """Return a compact prompt rule where persona remains the stable identity."""
    traits = "、".join(persona.personality[:4]) or "自然、稳定"
    parts = [f"表达基线始终是{traits}；当前情绪只能微调语速、措辞和回复长度，不能改变人格。"]

    if mood.mood in _LOW_MOODS:
        parts.append("低落时保留原本的说话习惯，只是更安静、更克制，不要突然变成陌生角色。")
    elif mood.mood in _HIGH_MOODS:
        parts.append("高唤醒情绪只提高表达强度；沉稳人设应克制，活泼人设可以更外放。")
    if mood.energy < 0.3:
        parts.append("精力较低，可以简短，但仍要保持称呼、口头禅和关系边界一致。")
    if mood_hint:
        parts.append(mood_hint)
    return "【人设与情绪融合】" + "".join(parts)
