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
    data/open_loops.json — 按用户分组
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from loguru import logger

from core.utils import atomic_write_json


# ---- 事件识别模式 ----

_EVENT_PATTERNS = [
    # 时间 + 事件
    (r"明天(.+?)(?:[。.！]|$)", 1),
    (r"下周(.+?)(?:[。.！]|$)", 7),
    (r"后天(.+?)(?:[。.！]|$)", 2),
    (r"下个月(.+?)(?:[。.！]|$)", 30),
    (r"周末(.+?)(?:[。.！]|$)", 5),
    (r"今晚(.+?)(?:[。.！]|$)", 0),
    (r"正在(.+?)(?:[。.！]|$)", 0),
    (r"最近(.+?)(?:[。.！]|$)", 0),
    (r"下个月(.+?)(?:[。.！]|$)", 30),
    (r"过两天(.+?)(?:[。.！]|$)", 2),
    # 状态描述
    (r"感冒了", 0),
    (r"生病了", 0),
    (r"发烧了", 0),
    (r"考试了", 0),
    (r"面试了", 0),
    (r"搬家了", 0),
    (r"毕业了", 0),
    (r"入职了", 0),
]

# 结束事件的关键词
_RESOLVE_KEYWORDS = [
    "考完了", "通过了", "挂科了", "失败了", "放弃了", "不去了",
    "结束了", "完成了", "搞定了", "好了", "痊愈了", "康复了",
    "取消了", "延期了", "推迟了",
]


@dataclass
class OpenLoop:
    """未完成事件"""
    id: str
    title: str           # 事件标题
    category: str        # 事件分类
    status: str = "pending"  # pending / resolved / failed / abandoned
    importance: int = 3
    expected_date: str | None = None  # 预计日期 ISO
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_asked: str | None = None     # 上次追问时间
    ask_count: int = 0                # 追问次数
    source_message: str = ""          # 来源消息

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "status": self.status,
            "importance": self.importance,
            "expected_date": self.expected_date,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_asked": self.last_asked,
            "ask_count": self.ask_count,
            "source_message": self.source_message,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OpenLoop":
        return cls(
            id=data["id"],
            title=data["title"],
            category=data.get("category", "other"),
            status=data.get("status", "pending"),
            importance=data.get("importance", 3),
            expected_date=data.get("expected_date"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            last_asked=data.get("last_asked"),
            ask_count=data.get("ask_count", 0),
            source_message=data.get("source_message", ""),
        )


class OpenLoopEngine:
    """未完成事件追踪引擎"""

    def __init__(self, data_dir: str | Path):
        self._data_dir = Path(data_dir)
        self._path = self._data_dir / "open_loops.json"
        self._loops: dict[str, list[OpenLoop]] = {}
        self._load()

    def _load(self):
        """加载持久化数据"""
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            for user_id, items in data.items():
                self._loops[user_id] = [OpenLoop.from_dict(i) for i in items]
        except Exception as e:
            logger.warning(f"Failed to load open loops: {e}")

    def _save(self):
        """持久化"""
        try:
            data = {
                uid: [l.to_dict() for l in loops]
                for uid, loops in self._loops.items()
            }
            atomic_write_json(self._path, data)
        except Exception as e:
            logger.error(f"Failed to save open loops: {e}")

    # ---- 事件识别 ----

    def detect(self, user_id: str, message: str) -> list[OpenLoop]:
        """从用户消息中检测未完成事件

        Returns:
            新创建的事件列表
        """
        created: list[OpenLoop] = []

        for pattern, days_offset in _EVENT_PATTERNS:
            match = re.search(pattern, message)
            if match:
                title = match.group(1).strip() if match.groups() else match.group(0).strip()
                if not title:
                    continue

                # 生成预计日期
                expected = None
                if days_offset > 0:
                    expected = (datetime.now() + timedelta(days=days_offset)).isoformat()

                loop = OpenLoop(
                    id=f"loop_{datetime.now().strftime('%Y%m%d%H%M%S')}_{len(created)}",
                    title=title,
                    category=self._classify(title),
                    expected_date=expected,
                    source_message=message,
                )

                # 检查是否已存在相同事件
                existing = self._find_similar(user_id, title)
                if not existing:
                    self._add(user_id, loop)
                    created.append(loop)
                    logger.info(f"OpenLoop created: {title}")

        # 检查是否有事件被解决
        self._check_resolved(user_id, message)

        return created

    def _classify(self, title: str) -> str:
        """分类事件"""
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
        """查找相似事件"""
        loops = self._loops.get(user_id, [])
        for loop in loops:
            if loop.status != "pending":
                continue
            # 简单匹配：标题包含关系
            if loop.title in title or title in loop.title:
                return loop
        return None

    def _add(self, user_id: str, loop: OpenLoop) -> None:
        """添加事件"""
        if user_id not in self._loops:
            self._loops[user_id] = []
        self._loops[user_id].append(loop)
        self._save()

    def _check_resolved(self, user_id: str, message: str) -> None:
        """检查用户消息是否解决了某个事件"""
        loops = self._loops.get(user_id, [])
        for loop in loops:
            if loop.status != "pending":
                continue
            # 检查消息中是否包含解决关键词
            if any(kw in message for kw in _RESOLVE_KEYWORDS):
                if loop.title in message or message in loop.source_message:
                    loop.status = "resolved"
                    loop.updated_at = datetime.now().isoformat()
                    logger.info(f"OpenLoop resolved: {loop.title}")
                    self._save()
                    break

    # ---- 追问 ----

    def get_follow_up(self, user_id: str) -> str | None:
        """获取需要追问的事件

        Returns:
            追问消息文本，如果没有则返回 None
        """
        loops = self._loops.get(user_id, [])
        now = datetime.now()

        for loop in loops:
            if loop.status != "pending":
                continue

            # 检查是否到了追问时间
            if loop.last_asked:
                last = datetime.fromisoformat(loop.last_asked)
                days_since = (now - last).total_seconds() / 86400
                # 第1次追问：24h，第2次：48h，之后停止
                if loop.ask_count == 0 and days_since < 1:
                    continue
                if loop.ask_count == 1 and days_since < 2:
                    continue
                if loop.ask_count >= 2:
                    continue
            else:
                # 首次追问：创建后 24h
                created = datetime.fromisoformat(loop.created_at)
                days_since = (now - created).total_seconds() / 86400
                if days_since < 1:
                    continue

            # 生成追问消息
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

    # ---- 查询 ----

    def get_pending(self, user_id: str) -> list[OpenLoop]:
        """获取用户的 pending 事件"""
        return [l for l in self._loops.get(user_id, []) if l.status == "pending"]

    def get_context(self, user_id: str) -> str:
        """生成 OpenLoop 上下文 prompt"""
        pending = self.get_pending(user_id)
        if not pending:
            return ""
        lines = ["【用户正在经历的事情】"]
        for loop in pending[:5]:
            status = "待完成" if loop.status == "pending" else loop.status
            lines.append(f"- {loop.title}（{status}）")
        return "\n".join(lines)

    def update_status(self, user_id: str, loop_id: str, status: str) -> bool:
        """手动更新事件状态"""
        loops = self._loops.get(user_id, [])
        for loop in loops:
            if loop.id == loop_id:
                loop.status = status
                loop.updated_at = datetime.now().isoformat()
                self._save()
                return True
        return False

    def expire_old(self, user_id: str, max_days: int = 30) -> int:
        """过期超过 max_days 的 pending 事件"""
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
