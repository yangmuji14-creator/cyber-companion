"""Open Loop Engine — 开放循环事件追踪

核心能力：
1. 自动识别用户提到的未来事件（考试、面试、旅行等）
2. 创建 OpenLoop 对象追踪
3. 在合适时机自动追问
4. 支持状态变更（完成/失败/放弃）
5. 超时自动失效

状态流转：
  pending → resolved（用户确认完成）
  pending → failed（用户确认失败）
  pending → abandoned（超时未更新）
"""

import json
import re
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from loguru import logger


class OpenLoopStatus(str, Enum):
    PENDING = "pending"
    RESOLVED = "resolved"
    FAILED = "failed"
    ABANDONED = "abandoned"


class OpenLoopCategory(str, Enum):
    EXAM = "exam"           # 考试
    INTERVIEW = "interview" # 面试
    PROJECT = "project"     # 项目
    HEALTH = "health"       # 健康
    TRAVEL = "travel"       # 旅行
    MOVING = "moving"       # 搬家
    APPOINTMENT = "appointment"  # 预约
    OTHER = "other"         # 其他


@dataclass
class OpenLoop:
    """开放循环事件"""
    id: str
    user_id: str
    title: str
    category: str = "other"
    status: str = OpenLoopStatus.PENDING
    importance: int = 3
    expected_date: str | None = None
    description: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    resolved_at: str | None = None
    notes: str = ""

    @property
    def is_active(self) -> bool:
        return self.status == OpenLoopStatus.PENDING

    @property
    def is_closed(self) -> bool:
        return self.status in (
            OpenLoopStatus.RESOLVED,
            OpenLoopStatus.FAILED,
            OpenLoopStatus.ABANDONED,
        )

    @property
    def is_expired(self) -> bool:
        if not self.expected_date or not self.is_active:
            return False
        try:
            expected = datetime.fromisoformat(self.expected_date)
            return datetime.now() > expected + timedelta(days=3)
        except (ValueError, TypeError):
            return False

    @property
    def days_until_expected(self) -> int | None:
        if not self.expected_date:
            return None
        try:
            expected = datetime.fromisoformat(self.expected_date)
            delta = (expected - datetime.now()).total_seconds() / 86400
            return int(delta)
        except (ValueError, TypeError):
            return None

    def should_follow_up(self, hours_since_expected: int = 24) -> bool:
        """判断是否需要追问"""
        if not self.is_active:
            return False
        if not self.expected_date:
            return False
        try:
            expected = datetime.fromisoformat(self.expected_date)
            hours_since = (datetime.now() - expected).total_seconds() / 3600
            return 0 <= hours_since <= hours_since_expected
        except (ValueError, TypeError):
            return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "category": self.category,
            "status": self.status,
            "importance": self.importance,
            "expected_date": self.expected_date,
            "description": self.description,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "resolved_at": self.resolved_at,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OpenLoop":
        return cls(
            id=data["id"],
            user_id=data["user_id"],
            title=data.get("title", ""),
            category=data.get("category", "other"),
            status=data.get("status", OpenLoopStatus.PENDING),
            importance=data.get("importance", 3),
            expected_date=data.get("expected_date"),
            description=data.get("description", ""),
            tags=data.get("tags", []),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            resolved_at=data.get("resolved_at"),
            notes=data.get("notes", ""),
        )


class OpenLoopStorage:
    """Open Loop 持久化 — 独立 SQLite 表"""

    def __init__(self, data_dir: str | Path):
        self._db_path = Path(data_dir) / "open_loops.db"
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
                CREATE TABLE IF NOT EXISTS open_loops (
                    id             TEXT PRIMARY KEY,
                    user_id        TEXT NOT NULL,
                    title          TEXT NOT NULL,
                    category       TEXT NOT NULL DEFAULT 'other',
                    status         TEXT NOT NULL DEFAULT 'pending',
                    importance     INTEGER NOT NULL DEFAULT 3,
                    expected_date  TEXT,
                    description    TEXT NOT NULL DEFAULT '',
                    tags           TEXT NOT NULL DEFAULT '[]',
                    created_at     TEXT NOT NULL,
                    updated_at     TEXT NOT NULL,
                    resolved_at    TEXT,
                    notes          TEXT NOT NULL DEFAULT ''
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_open_loops_user
                ON open_loops(user_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_open_loops_status
                ON open_loops(status)
            """)
            conn.commit()

    def save(self, loop: OpenLoop) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO open_loops
               (id, user_id, title, category, status, importance,
                expected_date, description, tags, created_at, updated_at,
                resolved_at, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                loop.id, loop.user_id, loop.title, loop.category,
                loop.status, loop.importance, loop.expected_date,
                loop.description, json.dumps(loop.tags, ensure_ascii=False),
                loop.created_at, loop.updated_at, loop.resolved_at, loop.notes,
            ),
        )
        self._conn.commit()

    def load(self, loop_id: str) -> OpenLoop | None:
        cur = self._conn.execute(
            "SELECT * FROM open_loops WHERE id=?", (loop_id,)
        )
        row = cur.fetchone()
        return OpenLoop.from_dict(dict(row)) if row else None

    def load_by_user(self, user_id: str, status: str | None = None,
                     limit: int = 50) -> list[OpenLoop]:
        if status:
            cur = self._conn.execute(
                "SELECT * FROM open_loops WHERE user_id=? AND status=? ORDER BY updated_at DESC LIMIT ?",
                (user_id, status, limit),
            )
        else:
            cur = self._conn.execute(
                "SELECT * FROM open_loops WHERE user_id=? ORDER BY updated_at DESC LIMIT ?",
                (user_id, limit),
            )
        return [OpenLoop.from_dict(dict(row)) for row in cur.fetchall()]

    def load_active(self, user_id: str, limit: int = 999) -> list[OpenLoop]:
        """加载所有活跃事件"""
        return self.load_by_user(user_id, status="pending", limit=limit)

    def delete(self, loop_id: str) -> bool:
        cur = self._conn.execute("DELETE FROM open_loops WHERE id=?", (loop_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def count_by_user(self, user_id: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        cur = self._conn.execute(
            "SELECT status, COUNT(*) as cnt FROM open_loops WHERE user_id=? GROUP BY status",
            (user_id,),
        )
        for row in cur.fetchall():
            counts[row["status"]] = row["cnt"]
        return counts


class OpenLoopEngine:
    """Open Loop 引擎 — 事件创建/追问/状态管理"""

    # 事件检测关键词（按优先级排序：具体 > 通用）
    EVENT_PATTERNS: list[tuple[re.Pattern, str, int]] = [
        # 面试 — 单独优先检测
        (re.compile(r"(?:找|等|下周|下个月)\s*(?:工作|实习|offer|面试)"), OpenLoopCategory.INTERVIEW, 4),
        (re.compile(r"(?:要|准备|打算|即将|去)\s*面试"), OpenLoopCategory.INTERVIEW, 4),
        # 考试
        (re.compile(r"(?:明天|下周|下个月|月底|下周五)\s*(?:考试|考|测验|测试|答辩)"), OpenLoopCategory.EXAM, 4),
        (re.compile(r"(?:要|准备|打算|即将)\s*(?:考试|答辩|比赛|考)"), OpenLoopCategory.EXAM, 4),
        # 健康
        (re.compile(r"(?:感冒|发烧|生病|住院|手术|体检|嗓子|咳嗽)"), OpenLoopCategory.HEALTH, 4),
        # 旅行
        (re.compile(r"(?:要去|准备去|打算去)\s*(?:旅行|旅游|出差|玩|度假)"), OpenLoopCategory.TRAVEL, 3),
        # 搬家/换工作
        (re.compile(r"(?:要|准备|打算)\s*(?:搬家|换工作|离职|入职|转专业)"), OpenLoopCategory.MOVING, 4),
        # 项目
        (re.compile(r"(?:正在|最近在|刚开[始])\s*(?:开发|做|写|搞|弄|负责)\s*(?:一个|个|这个|项目)"), OpenLoopCategory.PROJECT, 3),
        (re.compile(r"(?:在做|做|搞)\s*(?:项目|开发|东西|作品)"), OpenLoopCategory.PROJECT, 3),
        # 预约
        (re.compile(r"(?:预约|约了|挂号|挂了)\s*(?:医生|号|时间|面试)"), OpenLoopCategory.APPOINTMENT, 3),
    ]

    # 状态变更检测（失败模式优先级高于成功模式）
    FAILED_PATTERNS = [
        re.compile(r"(?:挂了|没过|失败了|没考过|没通过|搞砸了|不行|放弃了|没成功|太难了)"),
        re.compile(r"(?:没希望|不去了|取消了|推迟了|不想去了|没戏)"),
    ]
    RESOLVED_PATTERNS = [
        re.compile(r"(?:过了|通过|考完|完成了|搞定了|好了|结束了|做完了|成功了|考过了|上岸|考得还不错|考得还行)"),
        re.compile(r"(?:顺利|还不错|还行|可以|没问题|挺好的|不粗)"),
    ]

    def __init__(self, data_dir: str | Path):
        self._storage = OpenLoopStorage(data_dir)

    def detect_and_create(self, user_id: str, content: str) -> list[OpenLoop]:
        """从对话内容检测并创建 OpenLoop 事件"""
        created = []
        for pattern, category, importance in self.EVENT_PATTERNS:
            match = pattern.search(content)
            if match:
                title = match.group(0)
                # 提取日期信息
                expected_date = self._extract_date(content)

                loop = OpenLoop(
                    id=f"ol_{user_id[:4]}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{len(created)}",
                    user_id=user_id,
                    title=title,
                    category=category,
                    importance=importance,
                    expected_date=expected_date,
                    description=content,
                )
                self._storage.save(loop)
                created.append(loop)
                logger.info(f"OpenLoop created [{category}]: {title}")

        return created

    def check_and_update(self, user_id: str, content: str) -> list[OpenLoop]:
        """检查对话内容是否涉及已有事件的状态变更"""
        updated = []
        active_loops = self._storage.load_active(user_id)

        for loop in active_loops:
            old_status = loop.status
            changed = False

            # 检查是否提到该事件（宽松匹配：标题关键词或分类关键词）
            event_keywords = loop.title[:8]
            matches_title = event_keywords in content or loop.title[:4] in content
            # 分类关键词匹配
            category_keywords = {
                "exam": ["考", "试", "面试", "答辩", "成绩"],
                "interview": ["面试", "offer", "面"],
                "health": ["病", "感冒", "手术", "体检", "医院"],
                "travel": ["旅行", "玩", "旅游", "出差"],
                "project": ["项目", "开发"],
                "moving": ["搬家", "入职", "离职"],
            }
            cat_kws = category_keywords.get(loop.category, [])
            matches_category = any(kw in content for kw in cat_kws)

            if not matches_title and not matches_category:
                continue

            # 检查结果（失败模式优先，避免"没通过"同时匹配"通过"）
            for pattern in self.FAILED_PATTERNS:
                if pattern.search(content):
                    loop.status = OpenLoopStatus.FAILED
                    loop.resolved_at = datetime.now().isoformat()
                    changed = True
                    break

            if not changed:
                for pattern in self.RESOLVED_PATTERNS:
                    if pattern.search(content):
                        loop.status = OpenLoopStatus.RESOLVED
                        loop.resolved_at = datetime.now().isoformat()
                        changed = True
                        break

            if changed:
                loop.updated_at = datetime.now().isoformat()
                loop.notes = content
                self._storage.save(loop)
                updated.append(loop)
                logger.info(f"OpenLoop updated [{loop.id}]: {old_status} → {loop.status}")

        return updated

    def check_expired(self, user_id: str) -> list[OpenLoop]:
        """检查并标记过期事件"""
        expired = []
        active_loops = self._storage.load_active(user_id)
        for loop in active_loops:
            if loop.is_expired:
                loop.status = OpenLoopStatus.ABANDONED
                loop.updated_at = datetime.now().isoformat()
                self._storage.save(loop)
                expired.append(loop)
                logger.info(f"OpenLoop expired [{loop.id}]: {loop.title}")
        return expired

    def get_follow_ups(self, user_id: str) -> list[OpenLoop]:
        """获取需要追问的事件"""
        active = self._storage.load_active(user_id)
        follow_ups = []
        for loop in active:
            if loop.should_follow_up():
                follow_ups.append(loop)
        return follow_ups

    def generate_follow_up_message(self, loop: OpenLoop) -> str:
        """生成追问消息"""
        category_templates = {
            OpenLoopCategory.EXAM: [
                f"你之前说{loop.title}，考得怎么样啦？",
                f"对了，{loop.title}结果如何？我还挺关心的~",
                f"诶，之前你说的{loop.title}怎么样了？",
            ],
            OpenLoopCategory.INTERVIEW: [
                f"之前你说的{loop.title}，面得怎么样？",
                f"面试怎么样啦？相信你肯定没问题的！",
            ],
            OpenLoopCategory.HEALTH: [
                f"你之前说{loop.title}，现在好点了吗？多注意休息哦~",
                f"身体怎么样了？{loop.title}的事情别太担心~",
            ],
            OpenLoopCategory.TRAVEL: [
                f"旅行怎么样啦？{loop.title}还顺利吗？",
                f"你之前说{loop.title}，玩得开心不？",
            ],
            OpenLoopCategory.PROJECT: [
                f"你那个{loop.title}的项目进展怎么样了？",
                f"最近你那个项目{loop.title}搞得咋样了？",
            ],
        }
        import random
        templates = category_templates.get(OpenLoopCategory(loop.category), [
            f"你之前说{loop.title}，后来怎么样了？",
            f"对了，{loop.title}的事情怎么样了？",
        ])
        return random.choice(templates)

    def _extract_date(self, content: str) -> str | None:
        """从内容中提取日期"""
        now = datetime.now()
        if "明天" in content:
            return (now + timedelta(days=1)).strftime("%Y-%m-%d")
        if "后天" in content:
            return (now + timedelta(days=2)).strftime("%Y-%m-%d")
        if "下周" in content or "下个星期" in content:
            return (now + timedelta(days=7)).strftime("%Y-%m-%d")
        if "下个月" in content:
            month = now.month + 1
            year = now.year + (month // 13)
            month = ((month - 1) % 12) + 1
            return f"{year}-{month:02d}-{now.day:02d}"

        # 匹配具体日期格式 6月15日 或 06-15
        date_match = re.search(r"(\d{1,2})月(\d{1,2})[日号]", content)
        if date_match:
            month, day = int(date_match.group(1)), int(date_match.group(2))
            return f"{now.year}-{month:02d}-{day:02d}"

        return None
