"""记忆存储层 - SQLite 存储（替代 JSON）

线程安全（WAL 模式 + 连接隔离），支持并发读写。
自动从旧 JSON 文件迁移数据。

Schema:
  memories(
    user_id TEXT, id TEXT, content TEXT, level INT, category TEXT,
    created_at TEXT, last_accessed TEXT, access_count INT,
    tags TEXT, source TEXT, related_ids TEXT, superseded_by TEXT,
    PRIMARY KEY(user_id, id)
  )
"""

import json
import re
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from loguru import logger

from .models import Memory


class MemoryStorage:
    """SQLite 存储层

    每个数据库文件存储所有用户的记忆，按 user_id 分区。
    使用 WAL 模式 + 线程级连接隔离，支持并发读写。
    """

    def __init__(self, data_dir: str | Path):
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._data_dir / "memories.db"
        self._local = threading.local()
        self._write_counter = 0
        self._init_db()
        self._migrate_from_json()
        self._verify_integrity()

    # ---- 连接管理 ----

    @property
    def _conn(self) -> sqlite3.Connection:
        """线程级 SQLite 连接"""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            from core.storage.db import open_db
            self._local.conn = open_db(self._db_path)
        return self._local.conn

    def _init_db(self):
        """建表（线程安全）"""
        from core.storage.db import open_db
        with open_db(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    user_id        TEXT NOT NULL,
                    id             TEXT NOT NULL,
                    content        TEXT NOT NULL,
                    level          INTEGER NOT NULL DEFAULT 1,
                    category       TEXT NOT NULL DEFAULT 'other',
                    created_at     TEXT NOT NULL,
                    last_accessed  TEXT NOT NULL,
                    access_count   INTEGER NOT NULL DEFAULT 0,
                    tags           TEXT NOT NULL DEFAULT '[]',
                    source         TEXT NOT NULL DEFAULT 'auto',
                    related_ids    TEXT NOT NULL DEFAULT '[]',
                    superseded_by  TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (user_id, id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memories_user
                ON memories(user_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memories_level
                ON memories(user_id, level DESC)
            """)
            conn.commit()

    # ---- JSON 迁移 ----

    def _migrate_from_json(self):
        """从旧的 JSON 文件迁移数据（仅首次运行）"""
        json_dir = self._data_dir / "memories"
        if not json_dir.exists():
            return
        # 检查是否有任何 JSON 文件需要迁移
        json_files = list(json_dir.glob("*.json"))
        if not json_files:
            return
        # 检查 SQLite 是否已有数据
        cur = self._conn.execute("SELECT COUNT(*) FROM memories")
        if cur.fetchone()[0] > 0:
            logger.info("SQLite 已有数据，跳过 JSON 迁移")
            return
        migrated = 0
        for json_file in json_files:
            user_id = json_file.stem
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                memories = data.get("memories", [])
                for mem in memories:
                    self._insert(Memory.from_dict(mem), user_id)
                migrated += len(memories)
                # 迁移后重命名旧文件防止重复迁移
                json_file.rename(json_file.with_suffix(".json.migrated"))
            except Exception as e:
                logger.warning(f"迁移 {json_file.name} 失败: {e}")
        if migrated:
            logger.info(f"从 JSON 迁移了 {migrated} 条记忆到 SQLite")

    def _insert(self, memory: Memory, user_id: str | None = None):
        """插入一条记忆到数据库"""
        uid = user_id or "default"
        self._conn.execute(
            """INSERT OR REPLACE INTO memories
               (user_id, id, content, level, category, created_at,
                last_accessed, access_count, tags, source, related_ids, superseded_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                uid, memory.id, memory.content, memory.level,
                memory.category, memory.created_at, memory.last_accessed,
                memory.access_count, json.dumps(memory.tags, ensure_ascii=False),
                memory.source, json.dumps(memory.related_memory_ids),
                memory.superseded_by,
            ),
        )

    # ---- CRUD ----

    def load(self, user_id: str) -> list[Memory]:
        """加载用户的所有记忆"""
        cur = self._conn.execute(
            "SELECT * FROM memories WHERE user_id=? ORDER BY created_at DESC",
            (user_id,),
        )
        return [self._row_to_memory(row) for row in cur.fetchall()]

    def save(self, user_id: str, memories: list[Memory]) -> None:
        """保存用户的所有记忆（全量替换，事务内原子执行）"""
        conn = self._conn
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM memories WHERE user_id=?", (user_id,))
            for mem in memories:
                self._insert(mem, user_id)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def add(self, user_id: str, memory: Memory) -> None:
        """添加单条记忆"""
        self._insert(memory, user_id)
        self._conn.commit()
        self._maybe_checkpoint()

    def _maybe_checkpoint(self):
        """每 100 次写入触发一次 WAL 检点，防止 WAL 文件无限增长"""
        self._write_counter += 1
        if self._write_counter % 100 == 0:
            try:
                self._conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
            except Exception:
                pass

    def _verify_integrity(self):
        """数据库完整性检查（启动时运行）"""
        try:
            result = self._conn.execute("PRAGMA integrity_check").fetchone()
            if result and result[0] != "ok":
                logger.warning(f"DB integrity check: {result[0]}")
        except Exception as e:
            logger.warning(f"DB integrity check failed: {e}")

    def update(self, user_id: str, memory: Memory) -> None:
        """更新单条记忆"""
        self._insert(memory, user_id)
        self._conn.commit()

    def delete(self, user_id: str, memory_id: str) -> bool:
        """删除一条记忆"""
        cur = self._conn.execute(
            "DELETE FROM memories WHERE user_id=? AND id=?",
            (user_id, memory_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def get(self, user_id: str, memory_id: str) -> Memory | None:
        """获取单条记忆"""
        cur = self._conn.execute(
            "SELECT * FROM memories WHERE user_id=? AND id=?",
            (user_id, memory_id),
        )
        row = cur.fetchone()
        return self._row_to_memory(row) if row else None

    def search(self, user_id: str, keyword: str, limit: int = 20) -> list[Memory]:
        """关键词搜索记忆（LIKE 模糊匹配）"""
        cur = self._conn.execute(
            "SELECT * FROM memories WHERE user_id=? AND content LIKE ? "
            "ORDER BY level DESC, last_accessed DESC LIMIT ?",
            (user_id, f"%{keyword}%", limit),
        )
        return [self._row_to_memory(row) for row in cur.fetchall()]

    def delete_all(self, user_id: str) -> bool:
        """删除用户所有记忆"""
        cur = self._conn.execute(
            "DELETE FROM memories WHERE user_id=?", (user_id,)
        )
        self._conn.commit()
        return cur.rowcount > 0

    def count(self, user_id: str) -> int:
        """用户记忆数量"""
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM memories WHERE user_id=?", (user_id,)
        )
        return cur.fetchone()[0]

    def list_users(self) -> list[str]:
        """列出所有有记忆的用户"""
        cur = self._conn.execute(
            "SELECT DISTINCT user_id FROM memories"
        )
        return [row[0] for row in cur.fetchall()]

    def get_high_importance(self, user_id: str, min_level: int = 3, limit: int = 30) -> list[Memory]:
        """获取高重要度记忆"""
        cur = self._conn.execute(
            "SELECT * FROM memories WHERE user_id=? AND level>=? "
            "ORDER BY level DESC, last_accessed DESC LIMIT ?",
            (user_id, min_level, limit),
        )
        return [self._row_to_memory(row) for row in cur.fetchall()]

    def get_recent(self, user_id: str, limit: int = 20) -> list[Memory]:
        """获取最近记忆"""
        cur = self._conn.execute(
            "SELECT * FROM memories WHERE user_id=? "
            "ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        )
        return [self._row_to_memory(row) for row in cur.fetchall()]

    # ---- 工具方法 ----

    @staticmethod
    def _row_to_memory(row: sqlite3.Row) -> Memory:
        """将 SQLite 行转换为 Memory 对象"""
        return Memory(
            id=row["id"],
            content=row["content"],
            level=row["level"],
            category=row["category"],
            created_at=row["created_at"],
            last_accessed=row["last_accessed"],
            access_count=row["access_count"],
            tags=json.loads(row["tags"]) if isinstance(row["tags"], str) else row["tags"] or [],
            source=row["source"],
            related_memory_ids=json.loads(row["related_ids"]) if isinstance(row["related_ids"], str) else [],
            superseded_by=row["superseded_by"] or "",
        )

    def close(self):
        """关闭数据库连接，清理 WAL 文件"""
        if hasattr(self._local, "conn") and self._local.conn:
            try:
                self._local.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except Exception:
                pass
            try:
                self._local.conn.close()
            except Exception:
                pass
            self._local.conn = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
