"""统一数据库连接管理

基于 SQLite 最佳实践：
- 单文件 `companion.db`，WAL 模式
- 每个连接统一 PRAGMA 配置
- 线程本地连接，上下文管理器保证事务安全
- 引用：https://sqlite.org/appfileformat.html, https://sqlite.org/wal.html

用法:
    from core.storage.db import get_db, configure_connection

    with get_db("data/companion.db") as conn:
        conn.execute("SELECT * FROM mood_states WHERE user_id = ?", (user_id,))
"""

from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from loguru import logger

from .constants import CONSOLIDATED_DB_NAME
from .migrations import apply_schema_migrations


# 默认数据库路径
DEFAULT_DB_NAME = CONSOLIDATED_DB_NAME

# 统一 PRAGMA 配置（每个连接必须设置）
PRAGMA_CONFIG = {
    "journal_mode": "WAL",       # 写入前日志（已在使用 — 保留）
    "foreign_keys": "ON",        # ⚠ 关键：默认 OFF，必须显式开启
    "busy_timeout": 5000,        # 遇到锁时等待 5s，不直接报错
    "synchronous": "NORMAL",     # WAL 下安全，比 FULL 快 2-5x
    "cache_size": -64000,        # 64MB 缓存（默认仅 2MB）
    "temp_store": "MEMORY",      # 临时表放内存，减少 IO
    "mmap_size": 268435456,      # 256MB 内存映射，读更快
}

# 线程本地连接缓存
_local = threading.local()


def configure_connection(conn: sqlite3.Connection) -> None:
    """对连接应用统一 PRAGMA 配置。

    所有模块在打开连接后必须调用此函数。
    """
    conn.row_factory = sqlite3.Row
    for pragma, value in PRAGMA_CONFIG.items():
        try:
            if isinstance(value, str):
                conn.execute(f"PRAGMA {pragma}={value}")
            else:
                conn.execute(f"PRAGMA {pragma}={value}")
        except sqlite3.OperationalError as e:
            logger.warning(f"PRAGMA {pragma}={value} failed: {e}")


def open_db(db_path: str | Path) -> sqlite3.Connection:
    """打开数据库连接并应用统一配置。

    Args:
        db_path: 数据库文件路径

    Returns:
        已配置的 sqlite3.Connection
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    configure_connection(conn)
    apply_schema_migrations(conn)
    conn.commit()
    logger.debug(f"DB opened: {db_path}")
    return conn


def get_connection(db_path: str | Path = "") -> sqlite3.Connection:
    """获取线程本地的数据库连接（延迟创建）。

    同一线程多次调用返回相同连接。线程安全。

    Args:
        db_path: 数据库路径（为空时使用默认 data/companion.db）

    Returns:
        已配置的 sqlite3.Connection
    """
    if not db_path:
        from core.config import DATA_DIR
        db_path = DATA_DIR / DEFAULT_DB_NAME

    resolved = ":memory:" if str(db_path) == ":memory:" else str(Path(db_path).resolve())
    if not hasattr(_local, "connections"):
        _local.connections = {}
    conn = _local.connections.get(resolved)
    if conn is None:
        conn = open_db(resolved)
        _local.connections[resolved] = conn
    return conn


@contextmanager
def get_db(db_path: str | Path = "") -> Generator[sqlite3.Connection, None, None]:
    """上下文管理器：获取连接，自动提交/回滚。

    用法:
        with get_db() as conn:
            conn.execute("INSERT INTO ...")
        # 退出时自动 conn.commit()

        with get_db() as conn:
            conn.execute("INSERT INTO ...")
            raise ValueError("oops")
        # 异常时自动 conn.rollback()
    """
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def close_db() -> None:
    """关闭当前线程的数据库连接"""
    connections = getattr(_local, "connections", {})
    for conn in list(connections.values()):
        try:
            conn.close()
        except Exception:
            pass
    connections.clear()


def get_db_path(data_dir: str | Path = "", db_name: str = "") -> Path:
    """获取数据库文件路径（不打开连接）。

    Args:
        data_dir: 数据目录，默认 DATA_DIR
        db_name: 数据库文件名，默认 companion.db

    Returns:
        数据库文件的 Path
    """
    if not data_dir:
        from core.config import DATA_DIR
        data_dir = DATA_DIR
    if not db_name:
        db_name = DEFAULT_DB_NAME
    return Path(data_dir) / db_name
