"""Long Term Memory — 长期记忆（Layer 3）

保存：重要事实（用户喜欢猫、学计算机、喜欢Python等）
存储：SQLite + 向量索引
检索：语义搜索 + 关键词匹配
"""

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger


@dataclass
class LongTermFact:
    """长期事实"""
    id: str
    content: str                    # 事实内容
    category: str                   # 分类：personal, preference, event, opinion 等
    importance: int = 3             # 重要度 1-5
    confidence: float = 0.8         # 置信度 0-1
    source: str = "auto"            # 来源：auto, user, summary
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_accessed: str = field(default_factory=lambda: datetime.now().isoformat())
    access_count: int = 0
    tags: list[str] = field(default_factory=list)
    related_facts: list[str] = field(default_factory=list)  # 关联事实 ID

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "category": self.category,
            "importance": self.importance,
            "confidence": self.confidence,
            "source": self.source,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "access_count": self.access_count,
            "tags": self.tags,
            "related_facts": self.related_facts,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LongTermFact":
        return cls(
            id=data["id"],
            content=data["content"],
            category=data.get("category", "other"),
            importance=data.get("importance", 3),
            confidence=data.get("confidence", 0.8),
            source=data.get("source", "auto"),
            created_at=data.get("created_at", ""),
            last_accessed=data.get("last_accessed", ""),
            access_count=data.get("access_count", 0),
            tags=data.get("tags", []),
            related_facts=data.get("related_facts", []),
        )


class LongTermMemory:
    """长期记忆：重要事实的持久化存储"""

    def __init__(self, data_dir: str | Path):
        self._db_path = Path(data_dir) / "long_term.db"
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """初始化 SQLite 数据库"""
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS facts (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    category TEXT DEFAULT 'other',
                    importance INTEGER DEFAULT 3,
                    confidence REAL DEFAULT 0.8,
                    source TEXT DEFAULT 'auto',
                    created_at TEXT,
                    last_accessed TEXT,
                    access_count INTEGER DEFAULT 0,
                    tags TEXT DEFAULT '[]',
                    related_facts TEXT DEFAULT '[]'
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_category ON facts(category)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_importance ON facts(importance DESC)
            """)
            conn.commit()

    def add_fact(self, fact: LongTermFact) -> None:
        """添加一条长期事实"""
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO facts
                (id, content, category, importance, confidence, source,
                 created_at, last_accessed, access_count, tags, related_facts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                fact.id, fact.content, fact.category, fact.importance,
                fact.confidence, fact.source, fact.created_at,
                fact.last_accessed, fact.access_count,
                json.dumps(fact.tags, ensure_ascii=False),
                json.dumps(fact.related_facts),
            ))
            conn.commit()
        logger.debug(f"Added long-term fact: {fact.content[:30]}...")

    def get_fact(self, fact_id: str) -> LongTermFact | None:
        """获取一条事实"""
        with sqlite3.connect(str(self._db_path)) as conn:
            row = conn.execute(
                "SELECT * FROM facts WHERE id = ?", (fact_id,)
            ).fetchone()
            if not row:
                return None
            return self._row_to_fact(row)

    def search_by_keyword(self, keyword: str, limit: int = 10) -> list[LongTermFact]:
        """关键词搜索"""
        with sqlite3.connect(str(self._db_path)) as conn:
            rows = conn.execute(
                "SELECT * FROM facts WHERE content LIKE ? ORDER BY importance DESC LIMIT ?",
                (f"%{keyword}%", limit)
            ).fetchall()
            return [self._row_to_fact(row) for row in rows]

    def get_by_category(self, category: str, limit: int = 20) -> list[LongTermFact]:
        """按分类获取"""
        with sqlite3.connect(str(self._db_path)) as conn:
            rows = conn.execute(
                "SELECT * FROM facts WHERE category = ? ORDER BY importance DESC LIMIT ?",
                (category, limit)
            ).fetchall()
            return [self._row_to_fact(row) for row in rows]

    def get_important_facts(self, min_importance: int = 3, limit: int = 30) -> list[LongTermFact]:
        """获取重要事实"""
        with sqlite3.connect(str(self._db_path)) as conn:
            rows = conn.execute(
                "SELECT * FROM facts WHERE importance >= ? ORDER BY importance DESC, last_accessed DESC LIMIT ?",
                (min_importance, limit)
            ).fetchall()
            return [self._row_to_fact(row) for row in rows]

    def update_access(self, fact_id: str) -> None:
        """更新访问记录"""
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute("""
                UPDATE facts
                SET access_count = access_count + 1, last_accessed = ?
                WHERE id = ?
            """, (datetime.now().isoformat(), fact_id))
            conn.commit()

    def delete_fact(self, fact_id: str) -> bool:
        """删除一条事实"""
        with sqlite3.connect(str(self._db_path)) as conn:
            cursor = conn.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
            conn.commit()
            return cursor.rowcount > 0

    def get_context_prompt(self, query: str = "", limit: int = 10) -> str:
        """生成长期记忆上下文 prompt"""
        if query:
            facts = self.search_by_keyword(query, limit)
        else:
            facts = self.get_important_facts(limit=limit)

        if not facts:
            return ""

        lines = ["【关于用户的重要事实】"]
        for fact in facts:
            stars = "⭐" * fact.importance
            lines.append(f"- {stars} {fact.content}")

        return "\n".join(lines)

    def _row_to_fact(self, row: tuple) -> LongTermFact:
        """将数据库行转换为 LongTermFact"""
        return LongTermFact(
            id=row[0],
            content=row[1],
            category=row[2],
            importance=row[3],
            confidence=row[4],
            source=row[5],
            created_at=row[6],
            last_accessed=row[7],
            access_count=row[8],
            tags=json.loads(row[9]) if row[9] else [],
            related_facts=json.loads(row[10]) if row[10] else [],
        )

    @property
    def size(self) -> int:
        """获取事实总数"""
        with sqlite3.connect(str(self._db_path)) as conn:
            row = conn.execute("SELECT COUNT(*) FROM facts").fetchone()
            return row[0] if row else 0
