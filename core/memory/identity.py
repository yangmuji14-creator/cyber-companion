"""Identity Layer — 独立身份层

身份信息不属于普通记忆，不参与遗忘系统：
    - 教育背景
    - 专业
    - 兴趣爱好
    - 目标
    - 价值观
    - 性格特征
    - 重要人生事件

要求:
    - 独立存储（JSON 文件）
    - 不参与遗忘系统
    - Prompt 优先引用
    - 支持更新与冲突修正

存储:
    data/identities/{user_id}.json
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from core.utils import atomic_write_json


@dataclass
class IdentityProfile:
    """用户身份档案"""

    user_id: str

    # 基本信息
    education: str = ""           # 教育背景
    major: str = ""               # 专业
    school: str = ""              # 学校
    grade: str = ""               # 年级/届

    # 兴趣与性格
    interests: list[str] = field(default_factory=list)
    personality_traits: list[str] = field(default_factory=list)
    communication_style: str = ""  # 沟通风格

    # 目标与价值观
    goals: list[str] = field(default_factory=list)
    values: list[str] = field(default_factory=list)
    life_events: list[str] = field(default_factory=list)  # 重要人生事件

    # 偏好
    preferences: dict[str, Any] = field(default_factory=dict)

    # 元数据
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "education": self.education,
            "major": self.major,
            "school": self.school,
            "grade": self.grade,
            "interests": self.interests,
            "personality_traits": self.personality_traits,
            "communication_style": self.communication_style,
            "goals": self.goals,
            "values": self.values,
            "life_events": self.life_events,
            "preferences": self.preferences,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IdentityProfile":
        return cls(
            user_id=data.get("user_id", ""),
            education=data.get("education", ""),
            major=data.get("major", ""),
            school=data.get("school", ""),
            grade=data.get("grade", ""),
            interests=data.get("interests", []),
            personality_traits=data.get("personality_traits", []),
            communication_style=data.get("communication_style", ""),
            goals=data.get("goals", []),
            values=data.get("values", []),
            life_events=data.get("life_events", []),
            preferences=data.get("preferences", {}),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            version=data.get("version", 1),
        )

    def to_prompt(self) -> str:
        """生成身份档案 prompt 块"""
        parts = ["【用户身份档案】"]
        if self.education or self.school or self.major:
            parts.append(f"教育背景：{self.school} {self.education} {self.major}")
        if self.interests:
            parts.append(f"兴趣爱好：{', '.join(self.interests)}")
        if self.personality_traits:
            parts.append(f"性格特征：{', '.join(self.personality_traits)}")
        if self.goals:
            parts.append(f"目标：{', '.join(self.goals)}")
        if self.values:
            parts.append(f"价值观：{', '.join(self.values)}")
        if self.life_events:
            parts.append(f"重要经历：{', '.join(self.life_events)}")
        return "\n".join(parts)


class IdentityLayer:
    """身份层管理器"""

    def __init__(self, data_dir: str | Path):
        self._data_dir = Path(data_dir)
        self._path = self._data_dir / "identities"
        self._path.mkdir(parents=True, exist_ok=True)

    def _file_path(self, user_id: str) -> Path:
        """获取用户身份文件路径"""
        return self._path / f"{user_id}.json"

    def load(self, user_id: str) -> IdentityProfile:
        """加载用户身份档案"""
        path = self._file_path(user_id)
        if not path.exists():
            return IdentityProfile(user_id=user_id)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return IdentityProfile.from_dict(data)
        except Exception as e:
            logger.warning(f"Failed to load identity for {user_id}: {e}")
            return IdentityProfile(user_id=user_id)

    def save(self, profile: IdentityProfile) -> None:
        """保存用户身份档案"""
        profile.updated_at = datetime.now().isoformat()
        path = self._file_path(profile.user_id)
        atomic_write_json(path, profile.to_dict())

    def update(self, user_id: str, **kwargs) -> IdentityProfile:
        """更新身份档案字段"""
        profile = self.load(user_id)
        for key, value in kwargs.items():
            if hasattr(profile, key):
                setattr(profile, key, value)
        profile.version += 1
        self.save(profile)
        return profile

    def extract_from_message(self, user_id: str, message: str) -> IdentityProfile:
        """从消息中提取身份线索并更新档案

        简单的规则提取：
            - "我是学计算机的" → major="计算机"
            - "我喜欢Python" → interests += "Python"
            - "我在XX大学" → school="XX大学"
        """
        profile = self.load(user_id)
        changed = False

        # 专业
        major_patterns = [
            r"我是学(.+?)的",
            r"我学(.+?)的",
            r"专业是(.+?)(?:[。.！]|$)",
            r"读(.+?)专业",
        ]
        for pattern in major_patterns:
            match = __import__("re").search(pattern, message)
            if match:
                major = match.group(1).strip()
                if major and major != profile.major:
                    profile.major = major
                    changed = True
                break

        # 学校
        school_patterns = [
            r"在(.+?)(?:大学|学院|学校)(?:[。.！]|$)",
            r"(.+?)(?:大学|学院|学校)(?:[。.！]|$)",
        ]
        for pattern in school_patterns:
            match = __import__("re").search(pattern, message)
            if match:
                school = match.group(1).strip() + "大学"
                if school and school != profile.school:
                    profile.school = school
                    changed = True
                break

        # 兴趣
        interest_patterns = [
            r"我喜欢(.+?)(?:[。.！]|$)",
            r"我喜欢(.+?)和(.+?)(?:[。.！]|$)",
        ]
        for pattern in interest_patterns:
            match = __import__("re").search(pattern, message)
            if match:
                interests = [g.strip() for g in match.groups() if g.strip()]
                for i in interests:
                    if i and i not in profile.interests:
                        profile.interests.append(i)
                        changed = True
                break

        # 教育背景
        edu_keywords = {"大一": "大一", "大二": "大二", "大三": "大三", "大四": "大四",
                       "研究生": "研究生", "硕士": "硕士", "博士": "博士"}
        for kw, grade in edu_keywords.items():
            if kw in message and grade != profile.grade:
                profile.grade = grade
                changed = True

        if changed:
            self.save(profile)
            logger.info(f"Identity updated for {user_id}: {profile.to_dict()}")

        return profile

    def get_context(self, user_id: str) -> str:
        """获取身份档案上下文 prompt"""
        profile = self.load(user_id)
        prompt = profile.to_prompt()
        return prompt if "教育背景" in prompt or "兴趣" in prompt else ""
