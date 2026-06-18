"""身份画像 (flattened from core/identity/ package)

存储用户的稳定身份信息：
- 教育背景、专业、兴趣、目标、价值观
- 性格特征、重要人生事件
- 不参与遗忘系统
- Prompt 优先引用
"""

import json
import sqlite3
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger


@dataclass
class IdentityProfile:
    """用户身份画像 — 稳定、不参与遗忘"""

    user_id: str
    education: str = ""
    major: str = ""
    interests: list[str] = field(default_factory=list)
    goals: list[str] = field(default_factory=list)
    values: list[str] = field(default_factory=list)
    personality_traits: list[str] = field(default_factory=list)
    important_life_events: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    career: str = ""
    location: str = ""
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "education": self.education,
            "major": self.major,
            "interests": self.interests,
            "goals": self.goals,
            "values": self.values,
            "personality_traits": self.personality_traits,
            "important_life_events": self.important_life_events,
            "skills": self.skills,
            "career": self.career,
            "location": self.location,
            "updated_at": self.updated_at,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IdentityProfile":
        return cls(
            user_id=data.get("user_id", ""),
            education=data.get("education", ""),
            major=data.get("major", ""),
            interests=data.get("interests", []),
            goals=data.get("goals", []),
            values=data.get("values", []),
            personality_traits=data.get("personality_traits", []),
            important_life_events=data.get("important_life_events", []),
            skills=data.get("skills", []),
            career=data.get("career", ""),
            location=data.get("location", ""),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            created_at=data.get("created_at", datetime.now().isoformat()),
        )

    def merge(self, other: "IdentityProfile") -> "IdentityProfile":
        """合并另一个身份画像（新数据覆盖旧数据）"""
        merged = IdentityProfile(user_id=self.user_id)
        for field_name in (
            "education", "major", "career", "location"
        ):
            val = getattr(other, field_name) or getattr(self, field_name)
            setattr(merged, field_name, val)

        # 列表字段：合并去重
        for list_field in (
            "interests", "goals", "values",
            "personality_traits", "important_life_events", "skills",
        ):
            combined = list(set(getattr(self, list_field) + getattr(other, list_field)))
            setattr(merged, list_field, combined)

        merged.updated_at = datetime.now().isoformat()
        merged.created_at = self.created_at
        return merged

    def to_prompt_section(self) -> str:
        """生成 Prompt 段落 — 优先引用"""
        lines = ["【关于用户的稳定信息】（这些是确定的事实，不是短期记忆）"]
        if self.education:
            lines.append(f"- 教育背景：{self.education}")
        if self.major:
            lines.append(f"- 专业：{self.major}")
        if self.career:
            lines.append(f"- 职业：{self.career}")
        if self.location:
            lines.append(f"- 所在地：{self.location}")
        if self.interests:
            lines.append(f"- 兴趣：{'、'.join(self.interests)}")
        if self.goals:
            lines.append(f"- 目标：{'、'.join(self.goals)}")
        if self.values:
            lines.append(f"- 价值观：{'、'.join(self.values)}")
        if self.personality_traits:
            lines.append(f"- 性格特征：{'、'.join(self.personality_traits)}")
        if self.skills:
            lines.append(f"- 技能：{'、'.join(self.skills)}")
        if self.important_life_events:
            lines.append(f"- 重要人生事件：{'、'.join(self.important_life_events)}")
        return "\n".join(lines)


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
            conn = sqlite3.connect(str(self._db_path))
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return self._local.conn

    def _init_db(self):
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
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
            conn.commit()

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
                json.dumps(profile.values, ensure_ascii=False),  # value_traits column
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
                # 提取兴趣内容
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
