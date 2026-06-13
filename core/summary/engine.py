"""人生摘要引擎

每 50~100 轮对话自动生成：
- 近期状态
- 当前目标
- 项目进展
- 兴趣变化
- 情绪趋势
- 关系变化

保存为 LifeSummary 对象，注入 Prompt 提高长期连续性。
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
class LifeSummary:
    """人生摘要 — AI 自动生成的用户长期状态总结"""
    id: str
    user_id: str
    summary_type: str = "periodic"  # periodic / milestone / initial

    # 摘要内容
    recent_status: str = ""          # 近期状态
    current_goals: list[str] = field(default_factory=list)   # 当前目标
    project_progress: str = ""       # 项目进展
    interest_changes: str = ""       # 兴趣变化
    emotional_trends: str = ""       # 情绪趋势
    relationship_changes: str = ""   # 关系变化
    key_events: list[str] = field(default_factory=list)      # 关键事件

    # 元数据
    conversation_count: int = 0      # 生成时的聊天轮数
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    summary_text: str = ""           # 完整摘要文本（供 prompt 使用）

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "summary_type": self.summary_type,
            "recent_status": self.recent_status,
            "current_goals": self.current_goals,
            "project_progress": self.project_progress,
            "interest_changes": self.interest_changes,
            "emotional_trends": self.emotional_trends,
            "relationship_changes": self.relationship_changes,
            "key_events": self.key_events,
            "conversation_count": self.conversation_count,
            "created_at": self.created_at,
            "summary_text": self.summary_text,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LifeSummary":
        return cls(
            id=data.get("id", ""),
            user_id=data.get("user_id", ""),
            summary_type=data.get("summary_type", "periodic"),
            recent_status=data.get("recent_status", ""),
            current_goals=data.get("current_goals", []),
            project_progress=data.get("project_progress", ""),
            interest_changes=data.get("interest_changes", ""),
            emotional_trends=data.get("emotional_trends", ""),
            relationship_changes=data.get("relationship_changes", ""),
            key_events=data.get("key_events", []),
            conversation_count=data.get("conversation_count", 0),
            created_at=data.get("created_at", datetime.now().isoformat()),
            summary_text=data.get("summary_text", ""),
        )

    def to_prompt_section(self) -> str:
        """生成 Prompt 段落"""
        if self.summary_text:
            return f"【用户近期状态摘要】\n{self.summary_text}"

        lines = ["【用户近期状态摘要】"]
        if self.recent_status:
            lines.append(f"- 近期状态：{self.recent_status}")
        if self.current_goals:
            lines.append(f"- 当前目标：{'、'.join(self.current_goals)}")
        if self.project_progress:
            lines.append(f"- 项目进展：{self.project_progress}")
        if self.interest_changes:
            lines.append(f"- 兴趣变化：{self.interest_changes}")
        if self.emotional_trends:
            lines.append(f"- 情绪趋势：{self.emotional_trends}")
        if self.relationship_changes:
            lines.append(f"- 关系变化：{self.relationship_changes}")
        if self.key_events:
            lines.append(f"- 关键事件：{'、'.join(self.key_events[-5:])}")
        return "\n".join(lines)


class LifeSummaryStorage:
    """人生摘要持久化"""

    def __init__(self, data_dir: str | Path):
        self._db_path = Path(data_dir) / "life_summaries.db"
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
                CREATE TABLE IF NOT EXISTS life_summaries (
                    id                TEXT PRIMARY KEY,
                    user_id           TEXT NOT NULL,
                    summary_type      TEXT NOT NULL DEFAULT 'periodic',
                    recent_status     TEXT NOT NULL DEFAULT '',
                    current_goals     TEXT NOT NULL DEFAULT '[]',
                    project_progress  TEXT NOT NULL DEFAULT '',
                    interest_changes  TEXT NOT NULL DEFAULT '',
                    emotional_trends  TEXT NOT NULL DEFAULT '',
                    relationship_changes TEXT NOT NULL DEFAULT '',
                    key_events        TEXT NOT NULL DEFAULT '[]',
                    conversation_count INTEGER NOT NULL DEFAULT 0,
                    created_at        TEXT NOT NULL,
                    summary_text      TEXT NOT NULL DEFAULT ''
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_summaries_user
                ON life_summaries(user_id)
            """)
            conn.commit()

    def save(self, summary: LifeSummary) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO life_summaries
               (id, user_id, summary_type, recent_status, current_goals,
                project_progress, interest_changes, emotional_trends,
                relationship_changes, key_events, conversation_count,
                created_at, summary_text)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                summary.id, summary.user_id, summary.summary_type,
                summary.recent_status, json.dumps(summary.current_goals, ensure_ascii=False),
                summary.project_progress, summary.interest_changes,
                summary.emotional_trends, summary.relationship_changes,
                json.dumps(summary.key_events, ensure_ascii=False),
                summary.conversation_count, summary.created_at,
                summary.summary_text,
            ),
        )
        self._conn.commit()

    def load_latest(self, user_id: str) -> LifeSummary | None:
        cur = self._conn.execute(
            "SELECT * FROM life_summaries WHERE user_id=? ORDER BY created_at DESC LIMIT 1",
            (user_id,),
        )
        row = cur.fetchone()
        return LifeSummary.from_dict(dict(row)) if row else None

    def load_by_user(self, user_id: str, limit: int = 10) -> list[LifeSummary]:
        cur = self._conn.execute(
            "SELECT * FROM life_summaries WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        )
        return [LifeSummary.from_dict(dict(row)) for row in cur.fetchall()]

    def count_by_user(self, user_id: str) -> int:
        cur = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM life_summaries WHERE user_id=?",
            (user_id,),
        )
        return cur.fetchone()["cnt"]


class LifeSummaryEngine:
    """人生摘要生成引擎"""

    # 生成间隔（对话轮数）
    GENERATE_INTERVAL = 50

    def __init__(self, data_dir: str | Path):
        self._storage = LifeSummaryStorage(data_dir)

    def should_generate(self, user_id: str, conversation_count: int) -> bool:
        """判断是否需要生成新摘要"""
        latest = self._storage.load_latest(user_id)
        if latest is None:
            return conversation_count >= 10  # 首次：至少10轮
        return (conversation_count - latest.conversation_count) >= self.GENERATE_INTERVAL

    def generate_from_memories(self, user_id: str, conversation_count: int,
                               recent_memories: list[str]) -> LifeSummary:
        """基于记忆内容生成摘要（关键词规则版，无需 LLM）"""
        summary = LifeSummary(
            id=f"ls_{user_id[:4]}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            user_id=user_id,
            conversation_count=conversation_count,
        )

        all_text = " ".join(recent_memories) if recent_memories else ""

        # 近期状态
        status_keywords = {
            "忙": "近期比较忙碌",
            "累": "近期感到疲惫",
            "开心": "近期心情不错",
            "顺利": "近期运势不错",
            "烦": "近期有些烦恼",
            "加油": "正在努力中",
            "复习": "正在备考",
            "找工作": "正在找工作",
            "加班": "近期工作繁忙",
        }
        for kw, desc in status_keywords.items():
            if kw in all_text:
                summary.recent_status = desc
                break

        # 当前目标
        goal_patterns = ["想", "要", "打算", "准备", "希望", "计划", "目标"]
        for pattern in goal_patterns:
            for mem in recent_memories:
                if pattern in mem and len(mem) > 4:
                    summary.current_goals.append(mem.strip()[:30])
                    if len(summary.current_goals) >= 3:
                        break
            if len(summary.current_goals) >= 3:
                break

        # 关键事件
        event_keywords = ["考试", "面试", "搬家", "入职", "离职", "旅行",
                          "毕业", "结婚", "生日", "生病", "手术", "比赛"]
        for mem in recent_memories[:20]:
            for kw in event_keywords:
                if kw in mem and mem[:40] not in summary.key_events:
                    summary.key_events.append(mem.strip()[:40])
                    break

        # 情绪趋势
        positive = sum(1 for m in recent_memories if any(
            w in m for w in ["开心", "高兴", "顺利", "成功", "通过", "喜欢", "好"]))
        negative = sum(1 for m in recent_memories if any(
            w in m for w in ["难过", "伤心", "生气", "烦", "累", "不好", "失败"]))
        total = positive + negative
        if total > 0:
            ratio = positive / total
            if ratio >= 0.7:
                summary.emotional_trends = "整体积极向上"
            elif ratio >= 0.4:
                summary.emotional_trends = "有起有伏，总体平稳"
            else:
                summary.emotional_trends = "近期情绪较低落，需要关注"

        # 生成摘要文本
        parts = []
        if summary.recent_status:
            parts.append(summary.recent_status)
        if summary.current_goals:
            parts.append(f"当前目标：{'、'.join(summary.current_goals)}")
        if summary.emotional_trends:
            parts.append(f"情绪：{summary.emotional_trends}")
        if summary.key_events:
            parts.append(f"关键事件：{'、'.join(summary.key_events[-3:])}")

        summary.summary_text = "；".join(parts) if parts else "暂无足够信息生成摘要"
        self._storage.save(summary)
        logger.info(f"LifeSummary generated for {user_id} ({conversation_count} rounds)")
        return summary

    def get_latest(self, user_id: str) -> LifeSummary | None:
        return self._storage.load_latest(user_id)
