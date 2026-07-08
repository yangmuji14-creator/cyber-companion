"""VectorStore — SQLite 向量存储 + 余弦相似度 Top-K 搜索

结构：
  memories(user_id, memory_id, content, embedding_blob, created_at)

embedding 以 numpy float32 数组的二进制形式存入 SQLite，
检索时全量加载后用 numpy 矩阵运算算余弦相似度（500 条以内约 1-2ms）。
"""

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

import numpy as np
from loguru import logger


class VectorStore:
    """基于 SQLite 的向量存储引擎"""

    def __init__(self, db_path: str | Path):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_db()

    # ---- 连接管理 ----

    @property
    def _conn(self) -> sqlite3.Connection:
        """线程级连接"""
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
                    user_id    TEXT NOT NULL,
                    memory_id  TEXT NOT NULL,
                    content    TEXT NOT NULL,
                    embedding  BLOB NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, memory_id)
                )
            """)
            conn.commit()

    # ---- 核心操作 ----

    def add(self, user_id: str, memory_id: str, content: str,
            embedding: list[float], created_at: str | None = None) -> None:
        """存入一条向量记忆"""
        blob = np.array(embedding, dtype=np.float32).tobytes()
        if created_at is None:
            created_at = datetime.now().isoformat()
        self._conn.execute(
            "INSERT OR REPLACE INTO memories (user_id, memory_id, content, embedding, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, memory_id, content, blob, created_at),
        )
        self._conn.commit()

    def delete(self, user_id: str, memory_id: str) -> bool:
        """删除一条向量记忆"""
        cur = self._conn.execute(
            "DELETE FROM memories WHERE user_id=? AND memory_id=?",
            (user_id, memory_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def delete_all(self, user_id: str) -> int:
        """清空用户的所有向量记忆"""
        cur = self._conn.execute(
            "DELETE FROM memories WHERE user_id=?", (user_id,)
        )
        self._conn.commit()
        return cur.rowcount

    def count(self, user_id: str) -> int:
        """用户记忆数量"""
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM memories WHERE user_id=?", (user_id,)
        )
        return cur.fetchone()[0]

    def search(self, user_id: str, query_embedding: list[float],
               top_k: int = 5) -> list[dict]:
        """Top-K 语义搜索：余弦相似度

        Returns:
            [{memory_id, content, score, created_at}, ...]  按相似度降序
        """
        cur = self._conn.execute(
            "SELECT memory_id, content, embedding, created_at "
            "FROM memories WHERE user_id=?", (user_id,)
        )
        rows = cur.fetchall()
        if not rows:
            return []

        query_vec = np.array(query_embedding, dtype=np.float32).reshape(1, -1)

        results = []
        for memory_id, content, emb_blob, created_at in rows:
            mem_vec = np.frombuffer(emb_blob, dtype=np.float32).reshape(1, -1)
            # 余弦相似度（向量已 L2 归一化时等价于点积）
            score = float(np.dot(query_vec, mem_vec.T)[0, 0])
            results.append({
                "memory_id": memory_id,
                "content": content,
                "score": round(score, 4),
                "created_at": created_at,
            })

        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:top_k]

    def close(self):
        """关闭数据库连接，清理 WAL 文件"""
        if hasattr(self._local, "conn") and self._local.conn:
            try:
                self._local.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except Exception:
                pass
            self._local.conn.close()
            self._local.conn = None

    def list_all(self, user_id: str) -> list[dict]:
        """列出用户的所有向量记忆（不含 embedding 数据）"""
        cur = self._conn.execute(
            "SELECT memory_id, content, created_at FROM memories WHERE user_id=? "
            "ORDER BY created_at DESC",
            (user_id,),
        )
        return [
            {"memory_id": row[0], "content": row[1], "created_at": row[2]}
            for row in cur.fetchall()
        ]
