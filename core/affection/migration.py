"""JSON → SQLite 亲密度数据迁移工具

提供两个函数：
  - migrate_from_legacy()   — 应用启动时调用，将旧版 relationships.json
                              迁移到 UnifiedAffectionStorage（SQLite）
  - rollback_migration()    — 回滚：从 .bak 恢复原 JSON

安全特性：
  - 自动备份原 JSON（relationships.json.bak）
  - 标记文件 (migration_v1.json) 防止重复迁移
  - 逐条验证，单条失败不影响其他记录
  - 备份已存在时覆盖并记录警告

用法（app.py）：
    from core.affection.migration import migrate_from_legacy
    json_path = Path(data_dir) / "relationships.json"
    if json_path.exists():
        migrated = migrate_from_legacy(unified_storage, json_path)
        if migrated:
            logger.info("Legacy affection data migrated to unified storage")
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from core.affection.storage import UnifiedAffectionStorage


def migrate_from_legacy(
    storage: UnifiedAffectionStorage,
    json_path: str | Path,
) -> bool:
    """将 relationships.json 中的数据迁移到 UnifiedAffectionStorage。

    算法：
      1. 检查 json_path 是否存在 → 不存在则返回 False
      2. 检查迁移标记文件 migration_v1.json → 已存在则跳过
      3. 创建备份：复制 json_path → json_path.bak
      4. 读取并解析 JSON
      5. 遍历每条记录：
         - 解析键 → (user_id, persona_id)
         - 通过 INSERT OR IGNORE 写入（已存在的记录跳过）
         - 验证失败 / 写入异常 → 跳过该记录，记录警告
      6. 创建标记文件 data/migration_v1.json（时间戳）
      7. 返回是否至少有一条记录被成功迁移

    Args:
        storage: UnifiedAffectionStorage 实例（已连接 SQLite）
        json_path: 旧版 relationships.json 路径

    Returns:
        True 表示至少有一条记录迁移成功（或无需迁移），
        False 表示全部失败或文件不存在
    """
    json_path = Path(json_path)

    # 1. 检查文件是否存在
    if not json_path.exists():
        logger.debug(f"旧版亲密度文件不存在，跳过迁移: {json_path}")
        return False

    # 2. 检查迁移标记（幂等性）
    marker_path = json_path.parent / "migration_v1.json"
    if marker_path.exists():
        logger.info("迁移标记已存在，跳过本次迁移")
        return True

    # 3. 创建备份
    bak_path = json_path.with_suffix(".json.bak")
    if bak_path.exists():
        logger.warning(f"备份文件已存在，将被覆盖: {bak_path}")
    shutil.copy2(str(json_path), str(bak_path))
    logger.info(f"已创建备份: {bak_path}")

    # 4. 读取 JSON
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data: dict[str, Any] = json.load(f)
    except Exception as e:
        logger.warning(f"解析旧版 JSON 文件失败: {json_path} — {e}")
        return False

    if not data:
        logger.info("旧版 JSON 为空，无需迁移")
        _write_marker(marker_path)
        return True

    # 5. 逐条迁移
    migrated_count = 0
    error_count = 0

    for key, record in data.items():
        try:
            ok = _migrate_single(storage, key, record)
            if ok:
                migrated_count += 1
            else:
                error_count += 1
        except Exception as e:
            logger.warning(f"迁移记录失败 [{key}]: {e}")
            error_count += 1

    # 6. 创建标记文件
    if migrated_count > 0 or error_count == 0:
        _write_marker(marker_path)

    # 7. 返回结果
    if migrated_count == 0 and error_count > 0:
        logger.warning("所有记录均迁移失败")
        return False

    if error_count > 0:
        logger.warning(
            f"迁移完成，{migrated_count} 条成功，{error_count} 条失败"
        )
    else:
        logger.info(
            f"迁移完成，共 {migrated_count} 条记录"
        )

    return migrated_count > 0


def rollback_migration(json_path: str | Path) -> bool:
    """从 .bak 备份恢复原始 JSON 文件。

    Args:
        json_path: 原始 JSON 文件路径（自动查找同名的 .bak 文件）

    Returns:
        True 表示恢复成功，False 表示备份不存在
    """
    json_path = Path(json_path)
    bak_path = json_path.with_suffix(".json.bak")

    if not bak_path.exists():
        logger.warning(f"备份文件不存在，无法回滚: {bak_path}")
        return False

    shutil.copy2(str(bak_path), str(json_path))
    logger.info(f"已从备份恢复: {bak_path} → {json_path}")
    return True


# ── 内部辅助函数 ─────────────────────────────────────


def _parse_key(key: str) -> tuple[str, str]:
    """解析 JSON 键为 (user_id, persona_id)。

    "user1__tsundere" → ("user1", "tsundere")
    "user2"           → ("user2", "default")
    """
    if "__" in key:
        parts = key.split("__", 1)
        return parts[0], parts[1]
    return key, "default"


def _validate_record(record: dict[str, Any]) -> bool:
    """验证单条记录的必要字段类型。"""
    if not isinstance(record, dict):
        return False
    level = record.get("level", 50.0)
    if not isinstance(level, (int, float)):
        logger.warning(f"字段 'level' 类型无效: {type(level).__name__} = {level!r}")
        return False
    return True


def _migrate_single(
    storage: UnifiedAffectionStorage,
    key: str,
    record: dict[str, Any],
) -> bool:
    """迁移单条记录到 UnifiedAffectionStorage。

    使用 storage._conn 直接执行 INSERT OR IGNORE 以保证幂等性。
    返回 True 表示写入成功（或已存在被忽略），False 表示验证失败。
    """
    if not _validate_record(record):
        return False

    user_id, persona_id = _parse_key(key)

    level = record.get("level", 50.0)
    message_count = int(record.get("message_count", 0))
    positive_count = int(record.get("positive_count", 0))
    negative_count = int(record.get("negative_count", 0))
    now = datetime.now().isoformat()
    last_interaction = record.get("last_interaction", now)
    created_at = record.get("created_at", now)

    # 通过 storage._conn 执行 INSERT OR IGNORE
    storage._conn.execute(
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
    storage._conn.commit()
    return True


def _write_marker(marker_path: Path) -> None:
    """创建迁移标记文件，防止重复迁移。"""
    marker = {
        "version": 1,
        "migrated_at": datetime.now().isoformat(),
    }
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    with open(marker_path, "w", encoding="utf-8") as f:
        json.dump(marker, f, ensure_ascii=False, indent=2)
    logger.info(f"已创建迁移标记: {marker_path}")
