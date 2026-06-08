"""记忆数据模型"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Memory:
    """单条记忆"""

    id: str
    content: str
    level: int = 1  # 1-5 重要度
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_accessed: str = field(default_factory=lambda: datetime.now().isoformat())
    access_count: int = 0
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "level": self.level,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "access_count": self.access_count,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Memory":
        return cls(
            id=data["id"],
            content=data["content"],
            level=data.get("level", 1),
            created_at=data.get("created_at", datetime.now().isoformat()),
            last_accessed=data.get("last_accessed", datetime.now().isoformat()),
            access_count=data.get("access_count", 0),
            tags=data.get("tags", []),
        )

    def touch(self) -> None:
        """更新访问时间和次数"""
        self.last_accessed = datetime.now().isoformat()
        self.access_count += 1
