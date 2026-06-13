"""亲密度数据模型 — 记录、统计、SQL 表结构与存储接口"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class AffectionRecord:
    """亲密度记录 — 单条持久化数据"""
    user_id: str
    persona_id: str
    level: float
    message_count: int
    positive_count: int
    negative_count: int
    last_interaction: str
    created_at: str


@dataclass
class AffectionStats:
    """亲密度统计 — 概览信息"""
    level: float
    message_count: int
    positive_count: int
    negative_count: int
    days_known: int


CREATE_TABLE_SQL: str = """CREATE TABLE IF NOT EXISTS affection (
  user_id TEXT NOT NULL,
  persona_id TEXT NOT NULL DEFAULT 'default',
  level REAL NOT NULL DEFAULT 50.0,
  message_count INTEGER NOT NULL DEFAULT 0,
  positive_count INTEGER NOT NULL DEFAULT 0,
  negative_count INTEGER NOT NULL DEFAULT 0,
  last_interaction TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (user_id, persona_id)
);"""


from .storage import UnifiedAffectionStorage

@runtime_checkable
class AffectionStorage(Protocol):
    """亲密度存储接口 — 所有后端实现必须遵循此协议"""

    def get_level(self, user_id: str, persona_id: str = "default") -> float:
        """获取当前亲密度数值"""
        ...

    def update(
        self,
        user_id: str,
        direction: str,
        level: int,
        persona_id: str = "default",
    ) -> float:
        """更新亲密度并返回新值"""
        ...

    def get_stats(self, user_id: str, persona_id: str = "default") -> AffectionStats:
        """获取亲密度统计概览"""
        ...

    def get_last_interaction(
        self, user_id: str, persona_id: str = "default"
    ) -> str | None:
        """获取最近一次交互时间戳"""
        ...

    def apply_decay(self, user_id: str, persona_id: str = "default") -> float:
        """应用自然衰减并返回新值"""
        ...

    def migrate_from_json(self, json_path: str) -> bool:
        """从 JSON 文件迁移数据，成功返回 True"""
        ...
