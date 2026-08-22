"""人设加载器"""

import glob
import json
from pathlib import Path

from loguru import logger
from pydantic import ValidationError

from core.config import DATA_DIR
from core.utils import atomic_write_json
from .models import Persona


# T13: avatar 孤儿文件清理目录。本地定义避免循环 import
# （webui.server imports core.persona.loader，反向 import 会 cycle）。
_AVATAR_DIR = DATA_DIR / "avatars"


# 新版 Persona 字段的默认值（向后兼容旧版数据）
_PERSONA_DEFAULTS = {
    "hard_rules": [], "emotional_patterns": {}, "relationship_behavior": {},
    "taboos": [], "example_dialogs": [], "speaking_style": {},
    "mbti": "", "hometown": "", "occupation": "", "daily_routine": "",
    "appearance": "", "birthday": "", "catchphrases": [], "hobbies": [],
    "music_taste": "", "food_preferences": "", "nickname_for_user": "",
    "persona_prompt": "", "output_examples": "",
    "sticker_enabled": True, "sticker_probability": 0.18,
    "sticker_pack": "builtin",
}


def _ensure_defaults(data: dict) -> None:
    """为旧版 Persona 数据填充缺失的新字段默认值"""
    for key, default in _PERSONA_DEFAULTS.items():
        if key not in data:
            data[key] = default


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
                _ensure_defaults(p_data)
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
        "name", "age", "gender", "birthday", "avatar",
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
        "relationship_level", "system_prompt", "persona_prompt", "output_examples",
        "sticker_enabled", "sticker_probability", "sticker_pack",
        "hard_rules", "identity_anchor", "emotional_patterns", "relationship_behavior",
    "example_dialogs",
    }

    # 用户层字段（前端可直接编辑，无 prompt 工程风险）
    USER_FIELDS = {
        "name", "age", "gender", "birthday",
        "hometown", "occupation", "daily_routine", "appearance",
        "personality", "mbti", "hobbies",
        "music_taste", "movie_taste", "food_preferences",
        "catchphrases", "filler_words", "emoji_habits", "speech_rhythm",
        "nickname_for_user",
        "happy_expression", "sad_expression", "angry_expression",
        "jealous_expression", "shy_expression",
        "initiative_level", "clinginess", "jealous_tendency",
        "conflict_style", "affection_style",
        "pet_names", "favorite_topics", "avoided_topics", "question_tendency",
        "background", "relationship_level",
        "sticker_enabled", "sticker_probability", "sticker_pack",
    }

    # 高级字段（前端折叠区，需"如果不懂请保持默认"提示）
    ADVANCED_FIELDS = {
        "system_prompt", "persona_prompt", "output_examples", "hard_rules", "example_dialogs",
        "identity_anchor", "speaking_style", "emotional_patterns",
        "relationship_behavior", "core_memories", "legacy_speaking_style",
        "values", "taboos", "important_moments",
        "how_we_met", "first_impression",
    }

    def update(self, persona_id, **kwargs):
        persona = self._personas.get(persona_id)
        if not persona:
            return None
        clean = {
            key: value for key, value in kwargs.items()
            if key in self.ALLOWED_FIELDS
        }
        ignored = set(kwargs) - set(clean)
        for key in ignored:
            logger.warning(f"Ignored invalid field: {key}")
        try:
            # Validate a complete new model before replacing the in-memory copy.
            updated = Persona.model_validate({**persona.model_dump(), **clean})
        except ValidationError as e:
            logger.warning(f"Rejected invalid persona update for {persona_id}: {e}")
            return None
        self._personas[persona_id] = updated
        self._save()
        logger.info(f"Updated persona {persona_id}: {list(kwargs.keys())}")
        return updated

    def delete(self, persona_id):
        if persona_id in self._personas:
            del self._personas[persona_id]
            self._save()
            logger.info(f"Deleted persona {persona_id}")

            # T13: avatar orphan cleanup — 删除 persona 后清理其 avatar 文件。
            # glob 匹配 {persona_id}.* 所有扩展名（.png/.jpg/.webp 等）。
            avatar_pattern = str(_AVATAR_DIR / f"{persona_id}.*")
            for avatar_file in glob.glob(avatar_pattern):
                try:
                    Path(avatar_file).unlink()
                    logger.info(f"Avatar orphan cleaned: {avatar_file}")
                except Exception as e:
                    logger.warning(f"Failed to clean avatar {avatar_file}: {e}")

            return True
        return False

    def _save(self):
        data = {"personas": [p.to_dict() for p in self._personas.values()]}
        atomic_write_json(self._config_path, data)
        logger.debug(f"Saved {len(self._personas)} personas to {self._config_path}")
