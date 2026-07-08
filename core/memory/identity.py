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
import sqlite3
import threading
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
    career: str = ""              # 职业
    location: str = ""            # 所在地

    # 兴趣与性格
    interests: list[str] = field(default_factory=list)
    personality_traits: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    communication_style: str = ""  # 沟通风格

    # 目标与价值观
    goals: list[str] = field(default_factory=list)
    values: list[str] = field(default_factory=list)
    life_events: list[str] = field(default_factory=list)  # 重要人生事件
    important_life_events: list[str] = field(default_factory=list)  # 兼容旧名

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
            "career": self.career,
            "location": self.location,
            "interests": self.interests,
            "personality_traits": self.personality_traits,
            "skills": self.skills,
            "communication_style": self.communication_style,
            "goals": self.goals,
            "values": self.values,
            "life_events": self.life_events,
            "important_life_events": self.important_life_events,
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
            career=data.get("career", ""),
            location=data.get("location", ""),
            interests=data.get("interests", []),
            personality_traits=data.get("personality_traits", []),
            skills=data.get("skills", []),
            communication_style=data.get("communication_style", ""),
            goals=data.get("goals", []),
            values=data.get("values", []),
            life_events=data.get("life_events", []),
            important_life_events=data.get("important_life_events", []),
            preferences=data.get("preferences", {}),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            version=data.get("version", 1),
        )

    def merge(self, other: "IdentityProfile") -> "IdentityProfile":
        """合并另一个身份画像（新数据覆盖旧数据）"""
        merged = IdentityProfile(user_id=self.user_id)
        for field_name in (
            "education", "major", "career", "location", "school", "grade", "communication_style",
        ):
            val = getattr(other, field_name) or getattr(self, field_name)
            setattr(merged, field_name, val)

        # 列表字段：合并去重
        for list_field in (
            "interests", "goals", "values",
            "personality_traits", "life_events", "important_life_events",
            "skills",
        ):
            combined = list(set(getattr(self, list_field) + getattr(other, list_field)))
            setattr(merged, list_field, combined)

        # dict 字段：合并
        merged_prefs = {**getattr(self, "preferences", {}), **getattr(other, "preferences", {})}
        merged.preferences = merged_prefs

        merged.updated_at = datetime.now().isoformat()
        merged.created_at = self.created_at
        return merged

    def to_prompt(self) -> str:
        """生成身份档案 prompt 块"""
        parts = ["【用户身份档案】"]
        if self.education or self.school or self.major:
            parts.append(f"教育背景：{self.school} {self.education} {self.major}")
        if self.career:
            parts.append(f"职业：{self.career}")
        if self.location:
            parts.append(f"所在地：{self.location}")
        if self.interests:
            parts.append(f"兴趣爱好：{', '.join(self.interests)}")
        if self.personality_traits:
            parts.append(f"性格特征：{', '.join(self.personality_traits)}")
        if self.skills:
            parts.append(f"技能：{', '.join(self.skills)}")
        if self.goals:
            parts.append(f"目标：{', '.join(self.goals)}")
        if self.values:
            parts.append(f"价值观：{', '.join(self.values)}")
        if self.life_events:
            parts.append(f"重要经历：{', '.join(self.life_events)}")
        if self.important_life_events:
            parts.append(f"重要人生事件：{', '.join(self.important_life_events)}")
        return "\n".join(parts)

    def to_prompt_section(self) -> str:
        """生成 Prompt 段落 — 兼容旧版 API"""
        return self.to_prompt()


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


class IdentityStorage:
    """身份信息持久化 — 独立 SQLite 表

    特点：
    - 独立于记忆存储（不参与遗忘系统）
    - 每条用户只有一条记录（upsert）
    - WAL 模式 + 线程安全
    """

    def __init__(self, data_dir: str | Path):
        self._db_path = Path(data_dir) / "identity.db"
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_db()

    @property
    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            from core.storage.db import open_db
            self._local.conn = open_db(self._db_path)
        return self._local.conn

    def _init_db(self):
        from core.storage.db import open_db
        with open_db(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS identity (
                    user_id            TEXT PRIMARY KEY,
                    education          TEXT NOT NULL DEFAULT '',
                    major              TEXT NOT NULL DEFAULT '',
                    interests          TEXT NOT NULL DEFAULT '[]',
                    goals              TEXT NOT NULL DEFAULT '[]',
                    value_traits       TEXT NOT NULL DEFAULT '[]',
                    personality_traits TEXT NOT NULL DEFAULT '[]',
                    important_life_events TEXT NOT NULL DEFAULT '[]',
                    skills             TEXT NOT NULL DEFAULT '[]',
                    career             TEXT NOT NULL DEFAULT '',
                    location           TEXT NOT NULL DEFAULT '',
                    updated_at         TEXT NOT NULL,
                    created_at         TEXT NOT NULL
                )
            """)

    def load(self, user_id: str) -> IdentityProfile | None:
        """加载用户身份信息"""
        cur = self._conn.execute(
            "SELECT * FROM identity WHERE user_id=?",
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return IdentityProfile(
            user_id=row["user_id"],
            education=row["education"],
            major=row["major"],
            interests=json.loads(row["interests"]),
            goals=json.loads(row["goals"]),
            values=json.loads(row["value_traits"]),
            personality_traits=json.loads(row["personality_traits"]),
            important_life_events=json.loads(row["important_life_events"]),
            skills=json.loads(row["skills"]),
            career=row["career"],
            location=row["location"],
            updated_at=row["updated_at"],
            created_at=row["created_at"],
        )

    def save(self, profile: IdentityProfile) -> None:
        """保存或更新身份信息"""
        self._conn.execute(
            """INSERT OR REPLACE INTO identity
               (user_id, education, major, interests, goals, value_traits,
                personality_traits, important_life_events, skills,
                career, location, updated_at, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                profile.user_id,
                profile.education,
                profile.major,
                json.dumps(profile.interests, ensure_ascii=False),
                json.dumps(profile.goals, ensure_ascii=False),
                json.dumps(profile.values, ensure_ascii=False),
                json.dumps(profile.personality_traits, ensure_ascii=False),
                json.dumps(profile.important_life_events, ensure_ascii=False),
                json.dumps(profile.skills, ensure_ascii=False),
                profile.career,
                profile.location,
                profile.updated_at,
                profile.created_at,
            ),
        )
        self._conn.commit()
        logger.debug(f"Identity profile saved for {profile.user_id}")

    def delete(self, user_id: str) -> bool:
        """删除用户身份信息"""
        cur = self._conn.execute("DELETE FROM identity WHERE user_id=?", (user_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def list_users(self) -> list[str]:
        """列出所有有身份记录的用户"""
        cur = self._conn.execute("SELECT user_id FROM identity ORDER BY user_id")
        return [row["user_id"] for row in cur.fetchall()]

    def extract_from_content(self, user_id: str, content: str) -> IdentityProfile | None:
        """从对话内容中提取身份信息（关键词匹配）"""
        profile = self.load(user_id) or IdentityProfile(user_id=user_id)
        changed = False

        # 教育
        edu_keywords = {
            "大学生": "大学", "研究生": "研究生", "博士生": "博士",
            "高中": "高中", "初中": "初中", "小学": "小学",
            "本科": "本科", "硕士": "硕士", "博士": "博士",
        }
        for kw, val in edu_keywords.items():
            if kw in content and val not in profile.education:
                profile.education = val
                changed = True

        # 专业
        major_keywords = ["计算机", "软件", "数学", "物理", "化学", "生物",
                          "金融", "经济", "法律", "医学", "文学", "历史",
                          "机械", "电子", "建筑", "艺术", "设计", "英语"]
        for kw in major_keywords:
            if kw in content and kw not in profile.major:
                if profile.major:
                    profile.major += f"、{kw}"
                else:
                    profile.major = kw
                changed = True

        # 兴趣
        interest_keywords = ["喜欢", "爱好", "兴趣", "爱"]
        for kw in interest_keywords:
            idx = content.find(kw)
            if idx >= 0:
                rest = content[idx + len(kw):].strip("，。, .！!？?的")
                if rest and len(rest) < 20 and rest not in profile.interests:
                    profile.interests.append(rest)
                    changed = True

        # 职业
        career_keywords = {
            "程序员": "程序员", "工程师": "工程师", "老师": "老师",
            "医生": "医生", "律师": "律师", "设计师": "设计师",
            "产品经理": "产品经理", "运营": "运营", "销售": "销售",
        }
        for kw, val in career_keywords.items():
            if kw in content and val not in profile.career:
                profile.career = val
                changed = True

        if changed:
            profile.updated_at = datetime.now().isoformat()
            self.save(profile)
            logger.info(f"Identity extracted for {user_id}: {content[:30]}...")

        return profile if changed else None
