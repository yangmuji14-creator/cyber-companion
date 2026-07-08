"""SQLiteAffectionStorage — 独立 SQLite 亲密度存储（用于迁移测试与独立使用）

提供与 UnifiedAffectionStorage 兼容的 migrate_from_json 方法，
支持 JSON → SQLite 迁移、备份、幂等导入与部分失败回滚。

连接管理：每次 migrate_from_json 调用独立打开/关闭连接。
"""

from __future__ import annotations

import gc
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from core.social.affection.schema import CREATE_TABLE_SQL


class SQLiteAffectionStorage:
    """SQLite 亲密度存储（独立版）。

    封装 affection 表操作，提供从旧版 JSON 文件迁移数据的能力。
    连接在每次 migrate_from_json 调用时按需创建，调用完毕即关闭。

    Usage:
        storage = SQLiteAffectionStorage("data/affection.db")
        storage.migrate_from_json("data/relationships.json")
    """

    def __init__(self, db_path: str) -> None:
        """初始化，仅记录路径，不打开连接。

        Args:
            db_path: SQLite 数据库文件路径（如 /tmp/affection.db）
        """
        self.db_path = db_path

    # ── 连接管理 ────────────────────────────────────────

    def _open_conn(self) -> sqlite3.Connection:
        """创建并返回新的 SQLite 连接，确保表存在。"""
        from core.storage.db import open_db
        conn = open_db(self.db_path)
        conn.execute(CREATE_TABLE_SQL)
        conn.commit()
        return conn

    def _close_conn(self, conn: sqlite3.Connection | None) -> None:
        """安全关闭连接并强制释放文件锁（Windows 兼容）。"""
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
            # Windows 文件锁释放需要 GC + 控制权交还
            gc.collect()

    # ── 公开方法 ───────────────────────────────────────

    def migrate_from_json(self, json_path: str) -> bool:
        """从 JSON 文件迁移数据到 SQLite。

        算法：
          1. 检查 JSON 文件是否存在 → 不存在返回 False
          2. 创建备份 (relationships.json.bak)
          3. 读取并解析 JSON
          4. 遍历每条记录：
             a. 解析键 → (user_id, persona_id)
             b. 验证字段类型（level 必须为 int/float）
             c. 通过 INSERT OR IGNORE 写入 SQLite
             d. 失败则跳过该记录，继续处理后续
          5. 返回是否全部成功

        Args:
            json_path: 旧版 relationships.json 路径

        Returns:
            True 表示全部成功（或空 JSON），False 表示存在失败记录
        """
        json_path = Path(json_path)
        if not json_path.exists():
            return False

        # ── 创建备份 ────────────────────────────────────
        bak_path = json_path.with_suffix(".json.bak")
        if bak_path.exists():
            logger.warning(f"备份文件已存在，将被覆盖: {bak_path}")
        shutil.copy2(str(json_path), str(bak_path))

        # ── 读取 JSON ───────────────────────────────────
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data: dict[str, Any] = json.load(f)
        except Exception as e:
            logger.warning(f"解析 JSON 文件失败: {json_path} — {e}")
            return False

        # 空对象 → 直接成功（无数据需迁移）
        if not data:
            return True

        # ── 打开连接并逐条迁移 ───────────────────────────
        conn = self._open_conn()
        try:
            success_count = 0
            fail_count = 0

            for key, record in data.items():
                try:
                    ok = self._migrate_single_record(conn, key, record)
                    if ok:
                        success_count += 1
                    else:
                        fail_count += 1
                except Exception as e:
                    logger.warning(f"迁移记录失败 [{key}]: {e}")
                    fail_count += 1

            # 无成功记录且存在失败 → 完全失败
            if success_count == 0 and fail_count > 0:
                return False

            # 只要有一条失败就标记整体失败
            return fail_count == 0

        finally:
            self._close_conn(conn)

    # ── 内部方法 ───────────────────────────────────────

    @staticmethod
    def _parse_key(key: str) -> tuple[str, str]:
        """解析 JSON 键为 (user_id, persona_id)。

        "user1__tsundere" → ("user1", "tsundere")
        "user2"           → ("user2", "default")
        """
        if "__" in key:
            user_id, persona_id = key.split("__", 1)
        else:
            user_id = key
            persona_id = "default"
        return user_id, persona_id

    @staticmethod
    def _validate_record(record: dict[str, Any]) -> bool:
        """验证单条记录的字段类型。"""
        level = record.get("level", 50.0)
        if not isinstance(level, (int, float)):
            logger.warning(
                f"字段 'level' 类型无效: {type(level).__name__} = {level!r}"
            )
            return False
        return True

    def _migrate_single_record(
        self,
        conn: sqlite3.Connection,
        key: str,
        record: dict[str, Any],
    ) -> bool:
        """迁移单条记录到 SQLite。

        验证字段 → 解析键 → INSERT OR IGNORE。
        返回 True 表示成功（或被忽略），False 表示验证失败。
        """
        if not isinstance(record, dict):
            logger.warning(f"记录不是字典，跳过: {key}")
            return False

        # 字段类型验证
        if not self._validate_record(record):
            return False

        # 解析主键
        user_id, persona_id = self._parse_key(key)

        # 提取字段值
        level = record.get("level", 50.0)
        message_count = int(record.get("message_count", 0))
        positive_count = int(record.get("positive_count", 0))
        negative_count = int(record.get("negative_count", 0))
        now = datetime.now().isoformat()
        last_interaction = record.get("last_interaction", now)
        created_at = record.get("created_at", now)

        # INSERT OR IGNORE — 已存在的记录跳过（幂等性）
        conn.execute(
            """INSERT OR IGNORE INTO affection
               (user_id, persona_id, level, message_count,
                positive_count, negative_count, last_interaction, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id,
                persona_id,
                level,
                message_count,
                positive_count,
                negative_count,
                last_interaction,
                created_at,
            ),
        )
        conn.commit()
        return True
