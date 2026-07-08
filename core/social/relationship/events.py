"""关系事件 — 重要关系里程碑记录

记录：
- 第一次聊天
- 第一次主动安慰
- 重要项目讨论
- 重要情绪事件
- 共同回忆

用于未来引用：我记得你第一次和我聊这个项目的时候……
"""

import json
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger


@dataclass
class RelationshipEvent:
    """关系里程碑事件"""
    id: str
    user_id: str
    event_type: str  # first_chat / comfort / project / emotional / memory / other
    title: str
    description: str = ""
    importance: int = 3  # 1-5
    tags: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "event_type": self.event_type,
            "title": self.title,
            "description": self.description,
            "importance": self.importance,
            "tags": self.tags,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RelationshipEvent":
        return cls(
            id=data.get("id", ""),
            user_id=data.get("user_id", ""),
            event_type=data.get("event_type", "other"),
            title=data.get("title", ""),
            description=data.get("description", ""),
            importance=data.get("importance", 3),
            tags=data.get("tags", []),
            created_at=data.get("created_at", datetime.now().isoformat()),
        )


class RelationshipEventStorage:
    """关系事件持久化"""

    def __init__(self, data_dir: str | Path):
        self._db_path = Path(data_dir) / "relationship_events.db"
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
                CREATE TABLE IF NOT EXISTS relationship_events (
                    id          TEXT PRIMARY KEY,
                    user_id     TEXT NOT NULL,
                    event_type  TEXT NOT NULL,
                    title       TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    importance  INTEGER NOT NULL DEFAULT 3,
                    tags        TEXT NOT NULL DEFAULT '[]',
                    created_at  TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_re_events_user
                ON relationship_events(user_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_re_events_type
                ON relationship_events(event_type)
            """)
            conn.commit()

    def save(self, event: RelationshipEvent) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO relationship_events
               (id, user_id, event_type, title, description, importance, tags, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event.id, event.user_id, event.event_type, event.title,
                event.description, event.importance,
                json.dumps(event.tags, ensure_ascii=False),
                event.created_at,
            ),
        )
        self._conn.commit()

    def load_by_user(self, user_id: str, limit: int = 50) -> list[RelationshipEvent]:
        cur = self._conn.execute(
            "SELECT * FROM relationship_events WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        )
        return [RelationshipEvent.from_dict(dict(row)) for row in cur.fetchall()]

    def load_by_type(self, user_id: str, event_type: str, limit: int = 10) -> list[RelationshipEvent]:
        cur = self._conn.execute(
            "SELECT * FROM relationship_events WHERE user_id=? AND event_type=? ORDER BY created_at DESC LIMIT ?",
            (user_id, event_type, limit),
        )
        return [RelationshipEvent.from_dict(dict(row)) for row in cur.fetchall()]


class RelationshipEventTracker:
    """关系事件追踪器 — 自动检测并记录里程碑事件"""

    def __init__(self, data_dir: str | Path):
        self._storage = RelationshipEventStorage(data_dir)

    def detect_and_record(self, user_id: str, content: str, reply: str) -> list[RelationshipEvent]:
        """从对话内容检测并记录关系事件"""
        events = []

        # 1. 首次聊天
        existing = self._storage.load_by_type(user_id, "first_chat")
        if not existing:
            events.append(RelationshipEvent(
                id=f"re_first_{user_id[:4]}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                user_id=user_id,
                event_type="first_chat",
                title="第一次聊天",
                description=content[:50],
                importance=5,
            ))

        # 2. 安慰事件
        comfort_keywords = ["难过", "伤心", "哭", "不开心", "难受", "呜呜", "想哭"]
        for kw in comfort_keywords:
            if kw in content:
                events.append(RelationshipEvent(
                    id=f"re_comfort_{user_id[:4]}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    user_id=user_id,
                    event_type="comfort",
                    title="主动安慰",
                    description=f"用户表达'{kw}'情绪时给予了安慰",
                    importance=4,
                ))
                break

        # 3. 重要事件
        important_keywords = ["考试", "面试", "搬家", "入职", "离职",
                              "毕业", "手术", "结婚", "生日"]
        for kw in important_keywords:
            if kw in content:
                events.append(RelationshipEvent(
                    id=f"re_imp_{user_id[:4]}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    user_id=user_id,
                    event_type="emotional",
                    title=f"重要事件：{kw}",
                    description=content[:60],
                    importance=4,
                ))
                break

        # 4. 项目讨论
        project_keywords = ["项目", "开发", "在做", "负责", "写代码"]
        for kw in project_keywords:
            if kw in content:
                events.append(RelationshipEvent(
                    id=f"re_proj_{user_id[:4]}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    user_id=user_id,
                    event_type="project",
                    title="项目讨论",
                    description=content[:60],
                    importance=3,
                ))
                break

        for event in events:
            self._storage.save(event)
            logger.info(f"RelationshipEvent recorded [{event.event_type}]: {event.title}")

        return events

    def get_milestone_summary(self, user_id: str) -> str:
        """生成里程碑摘要用于 Prompt"""
        events = self._storage.load_by_user(user_id, limit=20)
        if not events:
            return ""

        lines = ["【你们的关系里程碑】"]
        for e in events[:10]:
            emoji_map = {
                "first_chat": "💫",
                "comfort": "💕",
                "emotional": "🌟",
                "project": "💻",
                "other": "📌",
            }
            emoji = emoji_map.get(e.event_type, "📌")
            lines.append(f"- {emoji} {e.title}（{e.created_at[:10]}）")
        return "\n".join(lines)
