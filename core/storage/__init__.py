"""core.storage — 统一存储层

提供集中式数据库连接管理、迁移、配置。
"""

from core.storage.db import (
    get_db, get_connection, configure_connection, open_db, close_db, get_db_path,
    DEFAULT_DB_NAME, PRAGMA_CONFIG,
)

from .backup import (
    BACKUP_FORMAT_VERSION,
    BackupValidationError,
    apply_pending_restore,
    create_backup,
    inspect_backup,
    pending_restore_status,
    restore_backup,
    schedule_restore,
)
from .constants import CONSOLIDATED_DB_NAME, LEGACY_DB_NAMES
from .migrations import (
    SCHEMA_VERSION,
    ConsolidationReport,
    apply_schema_migrations,
    consolidate_legacy_databases,
)

__all__ = [
    "get_db", "get_connection", "configure_connection", "open_db", "close_db",
    "get_db_path", "DEFAULT_DB_NAME", "PRAGMA_CONFIG",
    "BACKUP_FORMAT_VERSION", "BackupValidationError", "SCHEMA_VERSION",
    "CONSOLIDATED_DB_NAME", "LEGACY_DB_NAMES", "ConsolidationReport",
    "apply_schema_migrations", "consolidate_legacy_databases",
    "apply_pending_restore", "create_backup",
    "inspect_backup",
    "pending_restore_status",
    "restore_backup",
    "schedule_restore",
]
