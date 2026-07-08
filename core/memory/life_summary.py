"""Life Summary Engine — 长期人生摘要引擎

定期生成用户的人生摘要：
    - 近期状态
    - 当前目标
    - 项目进展
    - 兴趣变化
    - 情绪趋势
    - 关系变化

规则：
    - 每 50~100 轮对话自动生成
    - 保存为结构化数据
    - 用于提高长期连续性

存储:
    data/life_summaries/{user_id}.json — JSON 模式
    data/life_summaries.db — SQLite 模式（通过 LifeSummaryStorage）
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
class LifeSummary:
    """人生摘要（同时兼容 JSON 和 SQLite 模式）"""
    # 标识
    id: str = ""
    user_id: str = ""

    # 摘要类型
    summary_type: str = "periodic"  # periodic / milestone / initial

    # 摘要内容
    summary: str = ""               # 自然语言摘要（新 API）
    recent_status: str = ""         # 近期状态
    current_goals: list[str] = field(default_factory=list)
    project_progress: str = ""      # 项目进展（旧 API 字符串）
    project_progress_list: list[str] = field(default_factory=list)  # 新 API 列表
    interest_changes: str = ""      # 兴趣变化（旧 API 字符串）
    interest_changes_list: list[str] = field(default_factory=list)  # 新 API 列表
    emotional_trends: str = ""      # 情绪趋势（旧 API 字段名）
    emotion_trend: str = ""         # 情绪趋势（新 API 字段名）
    relationship_changes: str = ""

    # 关键事件
    key_events: list[str] = field(default_factory=list)

    # 元数据
    conversation_count: int = 0     # 旧 API
    message_count: int = 0          # 新 API
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    summary_text: str = ""          # 完整摘要文本（供 prompt 使用，旧 API）

    def __post_init__(self):
        """向后兼容：同步 emotion_trend ← emotional_trends"""
        if not self.emotion_trend and self.emotional_trends:
            self.emotion_trend = self.emotional_trends
        if not self.emotional_trends and self.emotion_trend:
            self.emotional_trends = self.emotion_trend
        # 向后兼容：同步 message_count ← conversation_count
        if self.conversation_count > 0 and self.message_count == 0:
            self.message_count = self.conversation_count
        if self.message_count > 0 and self.conversation_count == 0:
            self.conversation_count = self.message_count
        # 自动生成 id
        if not self.id and self.user_id:
            self.id = f"ls_{self.user_id[:4]}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        # 同步 summary_text
        if not self.summary_text and self.summary:
            self.summary_text = self.summary
        if not self.summary and self.summary_text:
            self.summary = self.summary_text

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "summary_type": self.summary_type,
            "summary": self.summary,
            "recent_status": self.recent_status,
            "current_goals": self.current_goals,
            "project_progress": self.project_progress,
            "project_progress_list": self.project_progress_list,
            "interest_changes": self.interest_changes,
            "interest_changes_list": self.interest_changes_list,
            "emotional_trends": self.emotional_trends,
            "emotion_trend": self.emotion_trend,
            "relationship_changes": self.relationship_changes,
            "key_events": self.key_events,
            "conversation_count": self.conversation_count,
            "message_count": self.message_count,
            "created_at": self.created_at,
            "summary_text": self.summary_text,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LifeSummary":
        return cls(
            id=data.get("id", ""),
            user_id=data.get("user_id", ""),
            summary_type=data.get("summary_type", "periodic"),
            summary=data.get("summary", ""),
            recent_status=data.get("recent_status", ""),
            current_goals=data.get("current_goals", []),
            project_progress=data.get("project_progress", ""),
            project_progress_list=data.get("project_progress_list", []),
            interest_changes=data.get("interest_changes", ""),
            interest_changes_list=data.get("interest_changes_list", []),
            emotional_trends=data.get("emotional_trends", ""),
            emotion_trend=data.get("emotion_trend", ""),
            relationship_changes=data.get("relationship_changes", ""),
            key_events=data.get("key_events", []),
            conversation_count=data.get("conversation_count", 0),
            message_count=data.get("message_count", 0),
            created_at=data.get("created_at", datetime.now().isoformat()),
            summary_text=data.get("summary_text", ""),
        )

    def to_prompt(self) -> str:
        """生成摘要 prompt（新 API）"""
        parts = ["【用户长期画像】"]
        if self.summary:
            parts.append(self.summary)
        if self.recent_status:
            parts.append(f"近期状态：{self.recent_status}")
        if self.current_goals:
            parts.append(f"当前目标：{', '.join(self.current_goals)}")
        if self.interest_changes or self.interest_changes_list:
            items = self.interest_changes_list or [self.interest_changes]
            parts.append(f"兴趣变化：{', '.join(items)}")
        if self.emotion_trend or self.emotional_trends:
            parts.append(f"情绪趋势：{self.emotion_trend or self.emotional_trends}")
        return "\n".join(parts)

    def to_prompt_section(self) -> str:
        """生成 Prompt 段落（旧 API）"""
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
        if self.emotional_trends or self.emotion_trend:
            lines.append(f"- 情绪趋势：{self.emotional_trends or self.emotion_trend}")
        if self.relationship_changes:
            lines.append(f"- 关系变化：{self.relationship_changes}")
        if self.key_events:
            lines.append(f"- 关键事件：{'、'.join(self.key_events[-5:])}")
        return "\n".join(lines)


# ========================================================================
# SQLite 存储（旧版 flattened 引擎用）
# ========================================================================

class LifeSummaryStorage:
    """人生摘要持久化 — SQLite"""

    def __init__(self, data_dir: str | Path):
        self._db_path = Path(data_dir) / "life_summaries.db"
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
                summary.emotional_trends or summary.emotion_trend,
                summary.relationship_changes,
                json.dumps(summary.key_events, ensure_ascii=False),
                summary.conversation_count or summary.message_count,
                summary.created_at,
                summary.summary_text or summary.summary,
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


# ========================================================================
# LifeSummaryEngine — 人生摘要引擎
# ========================================================================

class LifeSummaryEngine:
    """人生摘要引擎（JSON 模式，兼容旧版 SQLite 方法）"""

    GENERATE_INTERVAL = 50  # 旧 API 生成间隔

    def __init__(self, data_dir: str | Path):
        self._data_dir = Path(data_dir)
        # JSON 模式
        self._path = self._data_dir / "life_summaries"
        self._path.mkdir(parents=True, exist_ok=True)
        # SQLite 模式（旧 API 使用）
        self._sqlite_storage = LifeSummaryStorage(data_dir)
        # 兼容属性
        self._storage = self._sqlite_storage

    # ── JSON 模式 ──

    def _file_path(self, user_id: str) -> Path:
        return self._path / f"{user_id}.json"

    def load(self, user_id: str) -> LifeSummary:
        """加载摘要（JSON 模式）"""
        path = self._file_path(user_id)
        if not path.exists():
            return LifeSummary(user_id=user_id)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return LifeSummary.from_dict(data)
        except Exception as e:
            logger.warning(f"Failed to load life summary for {user_id}: {e}")
            return LifeSummary(user_id=user_id)

    def save(self, summary: LifeSummary) -> None:
        """保存摘要（JSON 模式）"""
        path = self._file_path(summary.user_id)
        atomic_write_json(path, summary.to_dict())

    def generate(self, user_id: str, messages: list[dict], memories: list[Any]) -> LifeSummary:
        """基于聊天历史和记忆生成摘要（JSON 模式）"""
        summary = self.load(user_id)
        msg_count = len(messages)
        if msg_count < 50:
            return summary

        emotions: dict[str, int] = {}
        for msg in messages:
            if isinstance(msg, dict) and "emotion" in msg:
                e = msg["emotion"]
                emotions[e] = emotions.get(e, 0) + 1

        if emotions:
            dominant = max(emotions, key=emotions.get)
            summary.emotion_trend = f"近期以{dominant}为主（{emotions[dominant]}次）"

        goals = []
        interests = []
        for mem in memories:
            if hasattr(mem, 'content'):
                content = mem.content
                if any(kw in content for kw in ["目标", "想", "计划", "打算"]):
                    goals.append(content)
                if any(kw in content for kw in ["喜欢", "爱好", "兴趣"]):
                    interests.append(content)

        summary.current_goals = goals[:5]
        summary.interest_changes_list = interests[:5]
        summary.message_count = msg_count
        summary.created_at = datetime.now().isoformat()

        parts = []
        if summary.emotion_trend:
            parts.append(summary.emotion_trend)
        if goals:
            parts.append(f"目标：{goals[0]}")
        if interests:
            parts.append(f"兴趣：{interests[0]}")
        summary.summary = "；".join(parts) if parts else ""

        self.save(summary)
        logger.info(f"LifeSummary generated for {user_id}: {summary.summary[:50]}...")
        return summary

    def get_context(self, user_id: str) -> str:
        """获取摘要上下文 prompt（JSON 模式）"""
        summary = self.load(user_id)
        if summary.message_count < 50:
            return ""
        return summary.to_prompt()

    def should_generate(self, user_id: str, conversation_count: int) -> bool:
        """判断是否应该生成新摘要（同时兼容 JSON 和 SQLite 存储）

        策略：
        - 先尝试 JSON 模式（message_count），有数据则用 >= 50 规则
        - 回退 SQLite 模式，首次 >= 10 轮返回 True
        - 后续 >= 50 轮间隔
        """
        summary = self.load(user_id)
        if summary.message_count > 0:
            return conversation_count - summary.message_count >= 50
        # 回退 SQLite 模式
        latest = self._sqlite_storage.load_latest(user_id)
        if latest is None:
            return conversation_count >= 10
        return (conversation_count - latest.conversation_count) >= self.GENERATE_INTERVAL

    def generate_from_memories(self, user_id: str, conversation_count: int,
                               recent_memories: list[str]) -> LifeSummary:
        """基于记忆内容生成摘要（旧 API，关键词规则版）"""
        summary = LifeSummary(
            id=f"ls_{user_id[:4]}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            user_id=user_id,
            conversation_count=conversation_count,
        )
        all_text = " ".join(recent_memories) if recent_memories else ""

        status_keywords = {
            "忙": "近期比较忙碌", "累": "近期感到疲惫",
            "开心": "近期心情不错", "顺利": "近期运势不错",
            "烦": "近期有些烦恼", "加油": "正在努力中",
            "复习": "正在备考", "找工作": "正在找工作",
            "加班": "近期工作繁忙",
        }
        for kw, desc in status_keywords.items():
            if kw in all_text:
                summary.recent_status = desc
                break

        goal_patterns = ["想", "要", "打算", "准备", "希望", "计划", "目标"]
        for pattern in goal_patterns:
            for mem in recent_memories:
                if pattern in mem and len(mem) > 4:
                    summary.current_goals.append(mem.strip()[:30])
                    if len(summary.current_goals) >= 3:
                        break
            if len(summary.current_goals) >= 3:
                break

        event_keywords = ["考试", "面试", "搬家", "入职", "离职", "旅行",
                          "毕业", "结婚", "生日", "生病", "手术", "比赛"]
        for mem in recent_memories[:20]:
            for kw in event_keywords:
                if kw in mem and mem[:40] not in summary.key_events:
                    summary.key_events.append(mem.strip()[:40])
                    break

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
        self._sqlite_storage.save(summary)
        logger.info(f"LifeSummary generated for {user_id} ({conversation_count} rounds)")
        return summary

    def get_latest(self, user_id: str) -> LifeSummary | None:
        """获取最新摘要（旧 API）"""
        return self._sqlite_storage.load_latest(user_id)
