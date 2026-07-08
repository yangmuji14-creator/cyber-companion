"""Open Loop Engine — 未完成事件追踪引擎

追踪用户提到的未来/进行中事件：
    - 明天考试
    - 下周面试
    - 正在开发项目
    - 最近感冒
    - 下个月旅行

功能:
    - 自动创建事件
    - 自动追问（24h/48h 后）
    - 自动结束（用户明确回答）
    - 超时失效
    - 状态变更

存储:
    data/open_loops.json — 按用户分组（JSON 模式）
    data/open_loops.db — SQLite 模式（通过 OpenLoopStorage）
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

from core.utils import atomic_write_json


# ========================================================================
# Enums
# ========================================================================

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


# ---- 事件识别模式（JSON 模式用） ----

_EVENT_PATTERNS_JSON = [
    (r"明天(.+?)(?:[。.！]|$)", 1),
    (r"下周(.+?)(?:[。.！]|$)", 7),
    (r"后天(.+?)(?:[。.！]|$)", 2),
    (r"下个月(.+?)(?:[。.！]|$)", 30),
    (r"周末(.+?)(?:[。.！]|$)", 5),
    (r"今晚(.+?)(?:[。.！]|$)", 0),
    (r"正在(.+?)(?:[。.！]|$)", 0),
    (r"最近(.+?)(?:[。.！]|$)", 0),
    (r"过两天(.+?)(?:[。.！]|$)", 2),
    (r"感冒了", 0), (r"生病了", 0), (r"发烧了", 0),
    (r"考试了", 0), (r"面试了", 0), (r"搬家了", 0), (r"毕业了", 0), (r"入职了", 0),
]

_RESOLVE_KEYWORDS = [
    "考完了", "通过了", "挂科了", "失败了", "放弃了", "不去了",
    "结束了", "完成了", "搞定了", "好了", "痊愈了", "康复了",
    "取消了", "延期了", "推迟了",
]


# ========================================================================
# OpenLoop 数据模型
# ========================================================================

@dataclass
class OpenLoop:
    """未完成事件（同时兼容 JSON 和 SQLite 模式）"""
    id: str
    user_id: str = ""
    title: str = ""
    category: str = "other"
    status: str = "pending"
    importance: int = 3
    expected_date: str | None = None
    description: str = ""
    tags: list[str] = field(default_factory=list)
    notes: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    resolved_at: str | None = None
    last_asked: str | None = None
    ask_count: int = 0
    source_message: str = ""

    # ── 属性 ──

    @property
    def is_active(self) -> bool:
        return self.status == OpenLoopStatus.PENDING

    @property
    def is_closed(self) -> bool:
        return self.status in (OpenLoopStatus.RESOLVED, OpenLoopStatus.FAILED, OpenLoopStatus.ABANDONED)

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

    # ── 序列化 ──

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
            "notes": self.notes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "resolved_at": self.resolved_at,
            "last_asked": self.last_asked,
            "ask_count": self.ask_count,
            "source_message": self.source_message,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OpenLoop":
        return cls(
            id=data["id"],
            user_id=data.get("user_id", ""),
            title=data.get("title", ""),
            category=data.get("category", "other"),
            status=data.get("status", "pending"),
            importance=data.get("importance", 3),
            expected_date=data.get("expected_date"),
            description=data.get("description", ""),
            tags=data.get("tags", []),
            notes=data.get("notes", ""),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            resolved_at=data.get("resolved_at"),
            last_asked=data.get("last_asked"),
            ask_count=data.get("ask_count", 0),
            source_message=data.get("source_message", ""),
        )


# ========================================================================
# SQLite 存储（兼容旧版 flattened 引擎）
# ========================================================================

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
            from core.storage.db import open_db
            self._local.conn = open_db(self._db_path)
        return self._local.conn

    def _init_db(self):
        from core.storage.db import open_db
        with open_db(self._db_path) as conn:
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


# ========================================================================
# OpenLoopEngine — 未完成事件追踪引擎
# ========================================================================

class OpenLoopEngine:
    """未完成事件追踪引擎（JSON 模式，兼容旧版 SQLite 方法）

    两类 API：
    - 新 API：detect() / get_follow_up() / get_pending() / get_context()
      → JSON 文件存储
    - 旧 API：detect_and_create() / check_and_update() / check_expired()
      → SQLite 存储（OpenLoopStorage）
    """

    # ---- 旧引擎常量（SQLite 模式使用） ----

    # 事件检测关键词（按优先级排序：具体 > 通用）
    EVENT_PATTERNS: list[tuple[re.Pattern, str, int]] = [
        (re.compile(r"(?:找|等|下周|下个月)\s*(?:工作|实习|offer|面试)"), OpenLoopCategory.INTERVIEW, 4),
        (re.compile(r"(?:要|准备|打算|即将|去)\s*面试"), OpenLoopCategory.INTERVIEW, 4),
        (re.compile(r"(?:明天|下周|下个月|月底|下周五)\s*(?:考试|考|测验|测试|答辩)"), OpenLoopCategory.EXAM, 4),
        (re.compile(r"(?:要|准备|打算|即将)\s*(?:考试|答辩|比赛|考)"), OpenLoopCategory.EXAM, 4),
        (re.compile(r"(?:感冒|发烧|生病|住院|手术|体检|嗓子|咳嗽)"), OpenLoopCategory.HEALTH, 4),
        (re.compile(r"(?:要去|准备去|打算去)\s*(?:旅行|旅游|出差|玩|度假)"), OpenLoopCategory.TRAVEL, 3),
        (re.compile(r"(?:要|准备|打算)\s*(?:搬家|换工作|离职|入职|转专业)"), OpenLoopCategory.MOVING, 4),
        (re.compile(r"(?:正在|最近在|刚开[始])\s*(?:开发|做|写|搞|弄|负责)\s*(?:一个|个|这个|项目)"), OpenLoopCategory.PROJECT, 3),
        (re.compile(r"(?:在做|做|搞)\s*(?:项目|开发|东西|作品)"), OpenLoopCategory.PROJECT, 3),
        (re.compile(r"(?:预约|约了|挂号|挂了)\s*(?:医生|号|时间|面试)"), OpenLoopCategory.APPOINTMENT, 3),
    ]

    FAILED_PATTERNS = [
        re.compile(r"(?:挂了|没过|失败了|没考过|没通过|搞砸了|不行|放弃了|没成功|太难了)"),
        re.compile(r"(?:没希望|不去了|取消了|推迟了|不想去了|没戏)"),
    ]
    RESOLVED_PATTERNS = [
        re.compile(r"(?:过了|通过|考完|完成了|搞定了|好了|结束了|做完了|成功了|考过了|上岸|考得还不错|考得还行)"),
        re.compile(r"(?:顺利|还不错|还行|可以|没问题|挺好的|不粗)"),
    ]

    def __init__(self, data_dir: str | Path):
        self._data_dir = Path(data_dir)
        # JSON 模式存储
        self._path = self._data_dir / "open_loops.json"
        self._loops: dict[str, list[OpenLoop]] = {}
        self._load()
        # SQLite 模式存储（旧 API 使用）
        self._sqlite_storage = OpenLoopStorage(data_dir)
        # 兼容属性：旧 API 可以直接访问 _storage
        self._storage = self._sqlite_storage

    # ── JSON 模式：持久化 ──

    def _load(self):
        """加载 JSON 持久化数据"""
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            for user_id, items in data.items():
                self._loops[user_id] = [OpenLoop.from_dict(i) for i in items]
        except Exception as e:
            logger.warning(f"Failed to load open loops: {e}")

    def _save(self):
        """持久化 JSON"""
        try:
            data = {
                uid: [l.to_dict() for l in loops]
                for uid, loops in self._loops.items()
            }
            atomic_write_json(self._path, data)
        except Exception as e:
            logger.error(f"Failed to save open loops: {e}")

    # ── 新 API：JSON 模式 ──

    def detect(self, user_id: str, message: str) -> list[OpenLoop]:
        """从用户消息中检测未完成事件（JSON 模式）"""
        created: list[OpenLoop] = []
        for pattern, days_offset in _EVENT_PATTERNS_JSON:
            match = re.search(pattern, message)
            if match:
                title = match.group(1).strip() if match.groups() else match.group(0).strip()
                if not title:
                    continue
                expected = None
                if days_offset > 0:
                    expected = (datetime.now() + timedelta(days=days_offset)).isoformat()
                loop = OpenLoop(
                    id=f"loop_{datetime.now().strftime('%Y%m%d%H%M%S')}_{len(created)}",
                    user_id=user_id,
                    title=title,
                    category=self._classify(title),
                    expected_date=expected,
                    source_message=message,
                )
                existing = self._find_similar(user_id, title)
                if not existing:
                    self._add(user_id, loop)
                    created.append(loop)
                    logger.info(f"OpenLoop created: {title}")
        self._check_resolved(user_id, message)
        return created

    def _classify(self, title: str) -> str:
        keywords = {
            "exam": ["考试", "测验", "笔试", "科目"],
            "interview": ["面试", "面经", "HR", "offer"],
            "travel": ["旅行", "旅游", "出差", "飞机", "酒店"],
            "health": ["感冒", "生病", "发烧", "医院", "体检", "手术"],
            "project": ["项目", "开发", "代码", "上线", "发布"],
            "move": ["搬家", "租房", "买房", "装修"],
            "study": ["学习", "考研", "雅思", "托福", "GRE"],
            "work": ["工作", "入职", "离职", "跳槽", "辞职"],
        }
        for cat, kws in keywords.items():
            if any(kw in title for kw in kws):
                return cat
        return "other"

    def _find_similar(self, user_id: str, title: str) -> OpenLoop | None:
        loops = self._loops.get(user_id, [])
        for loop in loops:
            if loop.status != "pending":
                continue
            if loop.title in title or title in loop.title:
                return loop
        return None

    def _add(self, user_id: str, loop: OpenLoop) -> None:
        if user_id not in self._loops:
            self._loops[user_id] = []
        self._loops[user_id].append(loop)
        self._save()

    def _check_resolved(self, user_id: str, message: str) -> None:
        loops = self._loops.get(user_id, [])
        for loop in loops:
            if loop.status != "pending":
                continue
            if any(kw in message for kw in _RESOLVE_KEYWORDS):
                if loop.title in message or message in loop.source_message:
                    loop.status = "resolved"
                    loop.updated_at = datetime.now().isoformat()
                    logger.info(f"OpenLoop resolved: {loop.title}")
                    self._save()
                    break

    def get_follow_up(self, user_id: str) -> str | None:
        """获取需要追问的事件（JSON 模式）"""
        loops = self._loops.get(user_id, [])
        now = datetime.now()
        for loop in loops:
            if loop.status != "pending":
                continue
            if loop.last_asked:
                last = datetime.fromisoformat(loop.last_asked)
                days_since = (now - last).total_seconds() / 86400
                if loop.ask_count == 0 and days_since < 1:
                    continue
                if loop.ask_count == 1 and days_since < 2:
                    continue
                if loop.ask_count >= 2:
                    continue
            else:
                created = datetime.fromisoformat(loop.created_at)
                days_since = (now - created).total_seconds() / 86400
                if days_since < 1:
                    continue
            loop.last_asked = now.isoformat()
            loop.ask_count += 1
            loop.updated_at = now.isoformat()
            self._save()
            templates = [
                f"{loop.title}怎么样了？",
                f"上次说的{loop.title}进行得顺利吗？",
                f"{loop.title}的结果出来了吗？",
            ]
            return templates[min(loop.ask_count - 1, len(templates) - 1)]
        return None

    def get_pending(self, user_id: str) -> list[OpenLoop]:
        """获取用户的 pending 事件（JSON 模式）"""
        return [l for l in self._loops.get(user_id, []) if l.status == "pending"]

    def get_context(self, user_id: str) -> str:
        """生成 OpenLoop 上下文 prompt（JSON 模式）"""
        pending = self.get_pending(user_id)
        if not pending:
            return ""
        lines = ["【用户正在经历的事情】"]
        for loop in pending[:5]:
            status = "待完成" if loop.status == "pending" else loop.status
            lines.append(f"- {loop.title}（{status}）")
        return "\n".join(lines)

    def update_status(self, user_id: str, loop_id: str, status: str) -> bool:
        """手动更新事件状态（JSON 模式）"""
        loops = self._loops.get(user_id, [])
        for loop in loops:
            if loop.id == loop_id:
                loop.status = status
                loop.updated_at = datetime.now().isoformat()
                self._save()
                return True
        return False

    def expire_old(self, user_id: str, max_days: int = 30) -> int:
        """过期超过 max_days 的 pending 事件（JSON 模式）"""
        loops = self._loops.get(user_id, [])
        now = datetime.now()
        expired = 0
        for loop in loops:
            if loop.status != "pending":
                continue
            created = datetime.fromisoformat(loop.created_at)
            days = (now - created).total_seconds() / 86400
            if days > max_days:
                loop.status = "abandoned"
                loop.updated_at = now.isoformat()
                expired += 1
        if expired:
            self._save()
        return expired

    # ── 旧 API：SQLite 模式（兼容） ──

    def detect_and_create(self, user_id: str, content: str) -> list[OpenLoop]:
        """从对话内容检测并创建 OpenLoop 事件（SQLite 模式）"""
        created = []
        for pattern, category, importance in self.EVENT_PATTERNS:
            match = pattern.search(content)
            if match:
                title = match.group(0)
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
                self._sqlite_storage.save(loop)
                created.append(loop)
                logger.info(f"OpenLoop created [{category}]: {title}")
        return created

    def check_and_update(self, user_id: str, content: str) -> list[OpenLoop]:
        """检查对话内容是否涉及已有事件的状态变更（SQLite 模式）"""
        updated = []
        active_loops = self._sqlite_storage.load_active(user_id)
        for loop in active_loops:
            old_status = loop.status
            changed = False
            event_keywords = loop.title[:8]
            matches_title = event_keywords in content or loop.title[:4] in content
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
                self._sqlite_storage.save(loop)
                updated.append(loop)
                logger.info(f"OpenLoop updated [{loop.id}]: {old_status} → {loop.status}")
        return updated

    def check_expired(self, user_id: str) -> list[OpenLoop]:
        """检查并标记过期事件（SQLite 模式）"""
        expired = []
        active_loops = self._sqlite_storage.load_active(user_id)
        for loop in active_loops:
            if loop.is_expired:
                loop.status = OpenLoopStatus.ABANDONED
                loop.updated_at = datetime.now().isoformat()
                self._sqlite_storage.save(loop)
                expired.append(loop)
                logger.info(f"OpenLoop expired [{loop.id}]: {loop.title}")
        return expired

    def get_follow_ups(self, user_id: str) -> list[OpenLoop]:
        """获取需要追问的事件（SQLite 模式）"""
        active = self._sqlite_storage.load_active(user_id)
        return [loop for loop in active if loop.should_follow_up()]

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
        date_match = re.search(r"(\d{1,2})月(\d{1,2})[日号]", content)
        if date_match:
            month, day = int(date_match.group(1)), int(date_match.group(2))
            return f"{now.year}-{month:02d}-{day:02d}"
        return None
