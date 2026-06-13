"""人设数据模型

支持丰富的角色属性，包括身份、性格、兴趣、语言习惯、情绪模式、行为倾向、关系背景等。
所有新字段都有默认值，向后兼容旧格式的 personas.json。
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Persona:
    """人设数据结构"""

    # === 基础信息 ===
    id: str
    name: str
    age: int = 20
    gender: str = "女"
    birthday: str = ""

    # === 身份细节 ===
    hometown: str = ""
    occupation: str = ""
    daily_routine: str = ""
    appearance: str = ""

    # === 性格 ===
    personality: list[str] = field(default_factory=list)
    mbti: str = ""
    values: list[str] = field(default_factory=list)
    taboos: list[str] = field(default_factory=list)

    # === 兴趣爱好 ===
    hobbies: list[dict[str, str]] = field(default_factory=list)
    music_taste: str = ""
    movie_taste: str = ""
    food_preferences: str = ""

    # === 语言习惯 ===
    catchphrases: list[str] = field(default_factory=list)
    filler_words: list[str] = field(default_factory=list)
    emoji_habits: str = ""
    speech_rhythm: str = ""
    nickname_for_user: str = ""

    # === 情绪模式 ===
    happy_expression: str = ""
    sad_expression: str = ""
    angry_expression: str = ""
    jealous_expression: str = ""
    shy_expression: str = ""

    # === 行为倾向 ===
    initiative_level: str = "中"
    clinginess: str = "中"
    jealous_tendency: str = "中"
    conflict_style: str = ""
    affection_style: str = ""

    # === 关系背景 ===
    how_we_met: str = ""
    first_impression: str = ""
    important_moments: list[str] = field(default_factory=list)
    pet_names: list[str] = field(default_factory=list)

    # === 沟通偏好 ===
    favorite_topics: list[str] = field(default_factory=list)
    avoided_topics: list[str] = field(default_factory=list)
    question_tendency: str = ""

    # === 旧字段保留（向后兼容） ===
    background: str = ""
    legacy_speaking_style: str = ""
    core_memories: list[str] = field(default_factory=list)
    relationship_level: int = 50
    system_prompt: str = ""

    # === Ex-skill 五层人设结构 ===
    hard_rules: list[str] = field(default_factory=list)             # L0: 不可违背的约束
    identity_anchor: dict = field(default_factory=dict)              # L1: MBTI, 星座, 关系描述
    speaking_style: dict = field(default_factory=dict)               # L2: catchphrases, filler_words, example_dialogues
    emotional_patterns: dict = field(default_factory=dict)           # L3: 依恋类型, love_language, triggers
    relationship_behavior: dict = field(default_factory=dict)        # L4: quarrel_pattern, boundaries

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "age": self.age,
            "personality": self.personality,
            "background": self.background,
            "legacy_speaking_style": self.legacy_speaking_style,
            "core_memories": self.core_memories,
            "relationship_level": self.relationship_level,
            "system_prompt": self.system_prompt,
        }
        new_fields = {
            "gender": self.gender, "birthday": self.birthday,
            "hometown": self.hometown, "occupation": self.occupation,
            "daily_routine": self.daily_routine, "appearance": self.appearance,
            "mbti": self.mbti, "values": self.values, "taboos": self.taboos,
            "hobbies": self.hobbies, "music_taste": self.music_taste,
            "movie_taste": self.movie_taste, "food_preferences": self.food_preferences,
            "catchphrases": self.catchphrases, "filler_words": self.filler_words,
            "emoji_habits": self.emoji_habits, "speech_rhythm": self.speech_rhythm,
            "nickname_for_user": self.nickname_for_user,
            "happy_expression": self.happy_expression, "sad_expression": self.sad_expression,
            "angry_expression": self.angry_expression, "jealous_expression": self.jealous_expression,
            "shy_expression": self.shy_expression,
            "initiative_level": self.initiative_level, "clinginess": self.clinginess,
            "jealous_tendency": self.jealous_tendency, "conflict_style": self.conflict_style,
            "affection_style": self.affection_style,
            "how_we_met": self.how_we_met, "first_impression": self.first_impression,
            "important_moments": self.important_moments, "pet_names": self.pet_names,
            "favorite_topics": self.favorite_topics, "avoided_topics": self.avoided_topics,
            "question_tendency": self.question_tendency,
            "hard_rules": self.hard_rules,
            "identity_anchor": self.identity_anchor,
            "speaking_style": self.speaking_style,
            "emotional_patterns": self.emotional_patterns,
            "relationship_behavior": self.relationship_behavior,
        }
        for key, value in new_fields.items():
            if isinstance(value, list):
                if value:
                    result[key] = value
            elif isinstance(value, str):
                if value:
                    result[key] = value
            elif value != "中":
                result[key] = value
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Persona":
        # Handle migration: old format had speaking_style as string under key "speaking_style"
        raw_speaking_style = data.get("speaking_style")
        if isinstance(raw_speaking_style, str):
            legacy_speaking_style = raw_speaking_style
            speaking_style = {}
        else:
            legacy_speaking_style = data.get("legacy_speaking_style", "")
            speaking_style = data.get("speaking_style", {})

        return cls(
            id=data["id"], name=data["name"], age=data.get("age", 20),
            gender=data.get("gender", "女"), birthday=data.get("birthday", ""),
            hometown=data.get("hometown", ""), occupation=data.get("occupation", ""),
            daily_routine=data.get("daily_routine", ""), appearance=data.get("appearance", ""),
            personality=data.get("personality", []), mbti=data.get("mbti", ""),
            values=data.get("values", []), taboos=data.get("taboos", []),
            hobbies=data.get("hobbies", []), music_taste=data.get("music_taste", ""),
            movie_taste=data.get("movie_taste", ""), food_preferences=data.get("food_preferences", ""),
            catchphrases=data.get("catchphrases", []), filler_words=data.get("filler_words", []),
            emoji_habits=data.get("emoji_habits", ""), speech_rhythm=data.get("speech_rhythm", ""),
            nickname_for_user=data.get("nickname_for_user", ""),
            happy_expression=data.get("happy_expression", ""),
            sad_expression=data.get("sad_expression", ""),
            angry_expression=data.get("angry_expression", ""),
            jealous_expression=data.get("jealous_expression", ""),
            shy_expression=data.get("shy_expression", ""),
            initiative_level=data.get("initiative_level", "中"),
            clinginess=data.get("clinginess", "中"),
            jealous_tendency=data.get("jealous_tendency", "中"),
            conflict_style=data.get("conflict_style", ""),
            affection_style=data.get("affection_style", ""),
            how_we_met=data.get("how_we_met", ""),
            first_impression=data.get("first_impression", ""),
            important_moments=data.get("important_moments", []),
            pet_names=data.get("pet_names", []),
            favorite_topics=data.get("favorite_topics", []),
            avoided_topics=data.get("avoided_topics", []),
            question_tendency=data.get("question_tendency", ""),
            background=data.get("background", ""),
            legacy_speaking_style=legacy_speaking_style,
            core_memories=data.get("core_memories", []),
            relationship_level=max(0, min(100, data.get("relationship_level", 50))),
            system_prompt=data.get("system_prompt", ""),
            hard_rules=data.get("hard_rules", []),
            identity_anchor=data.get("identity_anchor", {}),
            speaking_style=speaking_style,
            emotional_patterns=data.get("emotional_patterns", {}),
            relationship_behavior=data.get("relationship_behavior", {}),
        )
