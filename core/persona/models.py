"""人设数据模型"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Persona:
    """人设数据结构"""

    id: str
    name: str
    age: int = 20
    personality: list[str] = field(default_factory=list)
    background: str = ""
    speaking_style: str = ""
    core_memories: list[str] = field(default_factory=list)
    relationship_level: int = 50  # 0-100 亲密度
    system_prompt: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "age": self.age,
            "personality": self.personality,
            "background": self.background,
            "speaking_style": self.speaking_style,
            "core_memories": self.core_memories,
            "relationship_level": self.relationship_level,
            "system_prompt": self.system_prompt,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Persona":
        return cls(
            id=data["id"],
            name=data["name"],
            age=data.get("age", 20),
            personality=data.get("personality", []),
            background=data.get("background", ""),
            speaking_style=data.get("speaking_style", ""),
            core_memories=data.get("core_memories", []),
            relationship_level=data.get("relationship_level", 50),
            system_prompt=data.get("system_prompt", ""),
        )
