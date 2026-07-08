"""core.storage — 统一存储层

提供集中式数据库连接管理、迁移、配置。
"""

from core.storage.db import (
    get_db, get_connection, configure_connection, open_db, close_db, get_db_path,
    DEFAULT_DB_NAME, PRAGMA_CONFIG,
)

__all__ = [
    "get_db", "get_connection", "configure_connection", "open_db", "close_db",
    "get_db_path", "DEFAULT_DB_NAME", "PRAGMA_CONFIG",
]
