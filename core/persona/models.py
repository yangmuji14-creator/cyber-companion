"""Validated persona model with backward-compatible JSON serialization."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Persona(BaseModel):
    """A persona definition with one authoritative schema for validation and I/O.

    Existing ``personas.json`` files remain supported. ``to_dict`` intentionally
    preserves the compact on-disk format used by prior releases.
    """

    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    # Basic identity
    id: str
    name: str
    age: int = 20
    gender: str = "女"
    birthday: str = ""
    avatar: str = ""

    # Identity details
    hometown: str = ""
    occupation: str = ""
    daily_routine: str = ""
    appearance: str = ""

    # Personality and interests
    personality: list[str] = Field(default_factory=list)
    mbti: str = ""
    values: list[str] = Field(default_factory=list)
    taboos: list[str] = Field(default_factory=list)
    hobbies: list[dict[str, str]] = Field(default_factory=list)
    music_taste: str = ""
    movie_taste: str = ""
    food_preferences: str = ""

    # Speaking style
    catchphrases: list[str] = Field(default_factory=list)
    filler_words: list[str] = Field(default_factory=list)
    emoji_habits: str = ""
    speech_rhythm: str = ""
    nickname_for_user: str = ""

    # Emotional expression
    happy_expression: str = ""
    sad_expression: str = ""
    angry_expression: str = ""
    jealous_expression: str = ""
    shy_expression: str = ""

    # Relationship behavior
    initiative_level: str = "中"
    clinginess: str = "中"
    jealous_tendency: str = "中"
    conflict_style: str = ""
    affection_style: str = ""
    how_we_met: str = ""
    first_impression: str = ""
    important_moments: list[str] = Field(default_factory=list)
    pet_names: list[str] = Field(default_factory=list)
    favorite_topics: list[str] = Field(default_factory=list)
    avoided_topics: list[str] = Field(default_factory=list)
    question_tendency: str = ""

    # Legacy fields retained for existing users and prompts
    background: str = ""
    legacy_speaking_style: str = ""
    core_memories: list[str] = Field(default_factory=list)
    relationship_level: int = 50
    system_prompt: str = ""
    persona_prompt: str = ""
    output_examples: str = ""
    sticker_enabled: bool = True
    sticker_probability: float = 0.18
    sticker_pack: str = "builtin"

    # Ex-skill layered persona structure
    hard_rules: list[str] = Field(default_factory=list)
    identity_anchor: dict[str, Any] = Field(default_factory=dict)
    speaking_style: dict[str, Any] = Field(default_factory=dict)
    emotional_patterns: dict[str, Any] = Field(default_factory=dict)
    relationship_behavior: dict[str, Any] = Field(default_factory=dict)
    example_dialogs: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_speaking_style(cls, value: Any) -> Any:
        """Map the old string ``speaking_style`` field to its legacy location."""
        if not isinstance(value, dict):
            return value
        data = dict(value)
        if isinstance(data.get("speaking_style"), str):
            data.setdefault("legacy_speaking_style", data["speaking_style"])
            data["speaking_style"] = {}
        return data

    @field_validator("relationship_level", mode="before")
    @classmethod
    def clamp_relationship_level(cls, value: Any) -> int:
        try:
            return max(0, min(100, int(value)))
        except (TypeError, ValueError):
            return 50

    def to_dict(self) -> dict[str, Any]:
        """Serialize in the established compact format for ``personas.json``."""
        result = self.model_dump(exclude_defaults=True)
        # These legacy keys were always present in previous releases.
        for key in (
            "id", "name", "age", "gender", "personality", "background",
            "legacy_speaking_style", "core_memories", "relationship_level",
            "system_prompt",
            "persona_prompt", "output_examples",
        ):
            result[key] = getattr(self, key)
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Persona":
        """Compatibility entry point for callers and persisted persona files."""
        return cls.model_validate(data)
