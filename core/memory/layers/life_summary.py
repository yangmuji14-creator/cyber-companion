"""Life Summary — 生活总结（Layer 4）

AI 自动生成：
- 用户画像
- 长期目标
- 兴趣变化
- 关系变化

定期更新，存储为结构化数据
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from loguru import logger

from core.utils import atomic_write_json


@dataclass
class UserProfile:
    """用户画像"""
    interests: list[str] = field(default_factory=list)      # 兴趣爱好
    personality_traits: list[str] = field(default_factory=list)  # 性格特征
    communication_style: str = ""    # 沟通风格
    life_goals: list[str] = field(default_factory=list)     # 生活目标
    values: list[str] = field(default_factory=list)         # 价值观

    def to_dict(self) -> dict[str, Any]:
        return {
            "interests": self.interests,
            "personality_traits": self.personality_traits,
            "communication_style": self.communication_style,
            "life_goals": self.life_goals,
            "values": self.values,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UserProfile":
        return cls(
            interests=data.get("interests", []),
            personality_traits=data.get("personality_traits", []),
            communication_style=data.get("communication_style", ""),
            life_goals=data.get("life_goals", []),
            values=data.get("values", []),
        )


@dataclass
class InterestChange:
    """兴趣变化记录"""
    date: str
    interest: str
    change: str  # "新增"、"加强"、"减弱"、"消失"
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "interest": self.interest,
            "change": self.change,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InterestChange":
        return cls(
            date=data["date"],
            interest=data["interest"],
            change=data["change"],
            reason=data.get("reason", ""),
        )


@dataclass
class RelationshipChange:
    """关系变化记录"""
    date: str
    aspect: str   # "亲密度"、"信任度"、"依赖度" 等
    from_value: float
    to_value: float
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "aspect": self.aspect,
            "from_value": self.from_value,
            "to_value": self.to_value,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RelationshipChange":
        return cls(
            date=data["date"],
            aspect=data["aspect"],
            from_value=data["from_value"],
            to_value=data["to_value"],
            reason=data.get("reason", ""),
        )


class LifeSummary:
    """生活总结：AI 自动生成的用户画像和变化追踪"""

    def __init__(self, data_dir: str | Path):
        self._data_dir = Path(data_dir) / "life_summary"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._profile_path = self._data_dir / "profile.json"
        self._changes_path = self._data_dir / "changes.json"

        self._profile: UserProfile = UserProfile()
        self._interest_changes: list[InterestChange] = []
        self._relationship_changes: list[RelationshipChange] = []
        self._load()

    def _load(self):
        """加载数据"""
        if self._profile_path.exists():
            try:
                data = json.loads(self._profile_path.read_text(encoding="utf-8"))
                self._profile = UserProfile.from_dict(data)
            except Exception as e:
                logger.warning(f"Failed to load user profile: {e}")

        if self._changes_path.exists():
            try:
                data = json.loads(self._changes_path.read_text(encoding="utf-8"))
                self._interest_changes = [
                    InterestChange.from_dict(c) for c in data.get("interest_changes", [])
                ]
                self._relationship_changes = [
                    RelationshipChange.from_dict(c) for c in data.get("relationship_changes", [])
                ]
            except Exception as e:
                logger.warning(f"Failed to load changes: {e}")

    def _save(self):
        """保存数据"""
        try:
            atomic_write_json(self._profile_path, self._profile.to_dict())

            changes_data = {
                "interest_changes": [c.to_dict() for c in self._interest_changes[-50:]],
                "relationship_changes": [c.to_dict() for c in self._relationship_changes[-50:]],
            }
            atomic_write_json(self._changes_path, changes_data)
        except Exception as e:
            logger.error(f"Failed to save life summary: {e}")

    def update_profile(self, profile: UserProfile) -> None:
        """更新用户画像"""
        self._profile = profile
        self._save()
        logger.debug("Updated user profile")

    def add_interest_change(self, change: InterestChange) -> None:
        """记录兴趣变化"""
        self._interest_changes.append(change)
        if len(self._interest_changes) > 50:
            self._interest_changes = self._interest_changes[-50:]
        self._save()

    def add_relationship_change(self, change: RelationshipChange) -> None:
        """记录关系变化"""
        self._relationship_changes.append(change)
        if len(self._relationship_changes) > 50:
            self._relationship_changes = self._relationship_changes[-50:]
        self._save()

    def get_profile(self) -> UserProfile:
        """获取用户画像"""
        return self._profile

    def get_recent_interest_changes(self, days: int = 30) -> list[InterestChange]:
        """获取最近的兴趣变化"""
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        return [c for c in self._interest_changes if c.date >= cutoff]

    def get_recent_relationship_changes(self, days: int = 30) -> list[RelationshipChange]:
        """获取最近的关系变化"""
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        return [c for c in self._relationship_changes if c.date >= cutoff]

    def get_context_prompt(self) -> str:
        """生成生活总结上下文 prompt"""
        parts = []

        # 用户画像
        if self._profile.interests:
            parts.append(f"用户兴趣：{'、'.join(self._profile.interests[:5])}")
        if self._profile.personality_traits:
            parts.append(f"用户性格：{'、'.join(self._profile.personality_traits[:3])}")
        if self._profile.communication_style:
            parts.append(f"沟通风格：{self._profile.communication_style}")
        if self._profile.life_goals:
            parts.append(f"生活目标：{'、'.join(self._profile.life_goals[:3])}")

        # 最近变化
        recent_interests = self.get_recent_interest_changes(7)
        if recent_interests:
            changes = "、".join(f"{c.interest}({c.change})" for c in recent_interests[:3])
            parts.append(f"最近兴趣变化：{changes}")

        if not parts:
            return ""

        return "【关于用户的长期了解】\n" + "\n".join(parts)

    def to_dict(self) -> dict[str, Any]:
        """序列化"""
        return {
            "profile": self._profile.to_dict(),
            "interest_changes": [c.to_dict() for c in self._interest_changes],
            "relationship_changes": [c.to_dict() for c in self._relationship_changes],
        }
