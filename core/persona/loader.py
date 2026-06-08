"""人设加载器"""

import json
from pathlib import Path

from loguru import logger

from .models import Persona


class PersonaLoader:
    """人设加载器，负责从配置文件加载和管理人设"""

    def __init__(self, config_path: str | Path):
        self._config_path = Path(config_path)
        self._personas: dict[str, Persona] = {}
        self._load()

    def _load(self) -> None:
        """从 personas.json 加载所有人设"""
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

    def get(self, persona_id: str) -> Persona | None:
        """获取指定人设"""
        return self._personas.get(persona_id)

    def list_all(self) -> list[Persona]:
        """列出所有人设"""
        return list(self._personas.values())

    def add(self, persona: Persona) -> None:
        """添加新人设（内存 + 文件）"""
        self._personas[persona.id] = persona
        self._save()

    def update(self, persona_id: str, **kwargs) -> Persona | None:
        """更新人设属性"""
        persona = self._personas.get(persona_id)
        if not persona:
            return None

        for key, value in kwargs.items():
            if hasattr(persona, key):
                setattr(persona, key, value)

        self._save()
        logger.info(f"Updated persona {persona_id}: {list(kwargs.keys())}")
        return persona

    def delete(self, persona_id: str) -> bool:
        """删除人设"""
        if persona_id in self._personas:
            del self._personas[persona_id]
            self._save()
            logger.info(f"Deleted persona {persona_id}")
            return True
        return False

    def _save(self) -> None:
        """保存到 personas.json"""
        data = {"personas": [p.to_dict() for p in self._personas.values()]}
        with open(self._config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.debug(f"Saved {len(self._personas)} personas to {self._config_path}")
