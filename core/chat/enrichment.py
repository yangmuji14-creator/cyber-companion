"""User-message enrichment: emotion, mood, personality and relationship updates."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from loguru import logger

from core.emotion import EmotionAnalyzer
from core.emotion.llm_analyzer import _default_enriched


@dataclass
class EnrichmentResult:
    emotion: Any
    details: dict
    relationship_level: int
    thought: dict | None = None


class MessageEnricher:
    """Own the mutable analysis that happens before prompt construction."""

    def __init__(
        self,
        *,
        llm,
        emotion_analyzer,
        mood_engine,
        personality_engine,
        affection_storage,
        relationship_tracker,
        dialogue_thinker,
        chat_history,
    ) -> None:
        self._llm = llm
        self._emotion_analyzer = emotion_analyzer
        self._mood_engine = mood_engine
        self._personality_engine = personality_engine
        self._affection_storage = affection_storage
        self._relationship_tracker = relationship_tracker
        self._dialogue_thinker = dialogue_thinker
        self._chat_history = chat_history

    def preview(
        self,
        user_id: str,
        content: str,
        persona_id: str,
    ) -> EnrichmentResult:
        """Return instant local state for prompt assembly without mutating it."""
        emotion = EmotionAnalyzer.analyze(content)
        if self._affection_storage:
            relationship_level = int(
                self._affection_storage.get_level(user_id, persona_id)
            )
        else:
            relationship_level = 50
        return EnrichmentResult(
            emotion=emotion,
            details=_default_enriched(),
            relationship_level=relationship_level,
        )

    async def analyze(
        self,
        user_id: str,
        content: str,
        persona_id: str,
        persona,
        *,
        skip_user_message: bool = False,
    ) -> EnrichmentResult:
        if getattr(self._emotion_analyzer, "_llm", None) is None:
            self._emotion_analyzer._llm = self._llm

        async def analyze_thought() -> dict | None:
            if not self._dialogue_thinker:
                return None
            try:
                recent = None
                if not skip_user_message:
                    recent = self._chat_history.get_messages(user_id)[-6:]
                return await self._dialogue_thinker.think(
                    content,
                    recent_messages=recent,
                )
            except Exception as e:
                logger.debug(f"Dialogue thinker failed: {e}")
                return None

        emotion_result, thought = await asyncio.gather(
            self._emotion_analyzer.analyze(content),
            analyze_thought(),
        )
        emotion, details = emotion_result

        return EnrichmentResult(
            emotion=emotion,
            details=details,
            relationship_level=self.preview(
                user_id, content, persona_id,
            ).relationship_level,
            thought=thought,
        )

    def apply(
        self,
        user_id: str,
        persona_id: str,
        persona,
        result: EnrichmentResult,
    ) -> int:
        """Commit analyzed state after the concurrent main reply finishes."""
        emotion = result.emotion
        details = result.details
        if self._personality_engine:
            self._personality_engine.get_state(persona_id)
        if self._affection_storage:
            self._affection_storage.apply_decay(user_id, persona_id)
        if self._mood_engine:
            self._mood_engine.update_from_emotion(user_id, emotion)
        if self._personality_engine:
            self._personality_engine.update_from_llm(
                user_id,
                affection_impact=result.details.get("affection_impact"),
                personality_shift=result.details.get("personality_shift"),
            )

        affection_impact = result.details.get("affection_impact", {})
        if self._affection_storage:
            relationship_level = int(self._affection_storage.update(
                user_id,
                direction=affection_impact.get("direction", "neutral"),
                level=affection_impact.get("level", "low"),
                persona_id=persona_id,
            ))
        elif self._relationship_tracker:
            relationship_level = self._relationship_tracker.update(
                user_id,
                emotion=emotion.emotion.value,
                base_level=persona.relationship_level,
                persona_id=persona_id,
            )
        else:
            relationship_level = 50
        result.relationship_level = relationship_level
        return relationship_level
