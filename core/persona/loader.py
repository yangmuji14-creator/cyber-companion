"""人设加载器"""

import json
from pathlib import Path

from loguru import logger

from .models import Persona


class PersonaLoader:
    """人设加载器"""

    def __init__(self, config_path):
        self._config_path = Path(config_path)
        self._personas = {}
        self._load()

    def _load(self):
        if not self._config_path.exists():
            logger.warning(f"Personas config not found: {self._config_path}")
            return
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for p_data in data.get("personas", []):
                persona = Persona.from_dict(p_data)
                self._personas[persona.id] = persona
            logger.info(f"Loaded {len(self._personas)} personas: {list(self._personas.keys())}")
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to load personas: {e}")

    def get(self, persona_id):
        return self._personas.get(persona_id)

    def list_all(self):
        return list(self._personas.values())

    def add(self, persona):
        self._personas[persona.id] = persona
        self._save()

    ALLOWED_FIELDS = {
        "name", "age", "gender", "birthday",
        "hometown", "occupation", "daily_routine", "appearance",
        "personality", "mbti", "values", "taboos",
        "hobbies", "music_taste", "movie_taste", "food_preferences",
        "catchphrases", "filler_words", "emoji_habits",
        "speech_rhythm", "nickname_for_user",
        "happy_expression", "sad_expression", "angry_expression",
        "jealous_expression", "shy_expression",
        "initiative_level", "clinginess", "jealous_tendency",
        "conflict_style", "affection_style",
        "how_we_met", "first_impression", "important_moments", "pet_names",
        "favorite_topics", "avoided_topics", "question_tendency",
        "background", "speaking_style", "legacy_speaking_style", "core_memories",
        "relationship_level", "system_prompt",
        "hard_rules", "identity_anchor", "emotional_patterns", "relationship_behavior",
    }

    def update(self, persona_id, **kwargs):
        persona = self._personas.get(persona_id)
        if not persona:
            return None
        for key, value in kwargs.items():
            if key not in self.ALLOWED_FIELDS:
                logger.warning(f"Ignored invalid field: {key}")
                continue
            setattr(persona, key, value)
        self._save()
        logger.info(f"Updated persona {persona_id}: {list(kwargs.keys())}")
        return persona

    def delete(self, persona_id):
        if persona_id in self._personas:
            del self._personas[persona_id]
            self._save()
            logger.info(f"Deleted persona {persona_id}")
            return True
        return False

    def _save(self):
        data = {"personas": [p.to_dict() for p in self._personas.values()]}
        with open(self._config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.debug(f"Saved {len(self._personas)} personas to {self._config_path}")
