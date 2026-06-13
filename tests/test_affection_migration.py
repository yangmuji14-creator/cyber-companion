"""JSON→SQLite 数据迁移测试

测试场景覆盖：
  - 完整迁移（多用户 × 多人设）
  - 字段精度保持（浮点、整数、字符串）
  - 异常输入（文件不存在、JSON 损坏、空对象）
  - 备份与回滚机制
  - 幂等性（重复迁移不重复导入）
  - 部分失败回滚（单用户错误不影响其他用户）

旧 JSON 格式（data/relationships.json）：
    {"user_id__persona_id": {
        "level": float,
        "message_count": int,
        "positive_count": int,
        "negative_count": int,
        "last_interaction": str,
        "created_at": str
    }}

SQLite 目标表（affection）：
    CREATE TABLE affection (
      user_id TEXT, persona_id TEXT, level REAL,
      message_count INTEGER, positive_count INTEGER,
      negative_count INTEGER, last_interaction TEXT,
      created_at TEXT,
      PRIMARY KEY (user_id, persona_id)
    );

预期：Task 12 实现 SQLiteAffectionStorage 后该文件应全部通过。
当前阶段（未实现）：导入会失败 → RED。
"""

import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.affection.schema import CREATE_TABLE_SQL, AffectionRecord

# ──────────────────────────────────────────────────────
# Task 12 将在 core/affection/sqlite_storage.py 中提供
# SQLiteAffectionStorage 类。
# 在此之前，此导入会抛出 ModuleNotFoundError → RED。
# ──────────────────────────────────────────────────────
from core.affection.sqlite_storage import SQLiteAffectionStorage


# ══════════════════════════════════════════════════════
# 测试数据工厂
# ══════════════════════════════════════════════════════

def build_record(**overrides: object) -> dict[str, object]:
    """构造一条符合旧 JSON 格式的亲密度记录（默认值 + 可覆盖）。"""
    data: dict[str, object] = {
        "level": 50.0,
        "message_count": 0,
        "positive_count": 0,
        "negative_count": 0,
        "last_interaction": "2026-01-01T00:00:00.000000",
        "created_at": "2026-01-01T00:00:00.000000",
    }
    data.update(overrides)
    return data


def build_json_data(
    entries: list[tuple[str, str, dict[str, object]]],
) -> dict[str, dict[str, object]]:
    """将 (user_id, persona_id, overrides) 列表组装为旧 JSON 格式。

    Args:
        entries: 每个元素为 (user_id, persona_id, record_overrides)
                 当 persona_id 为空字符串时，键不包含 __ 后缀
    Returns:
        可直接 json.dump 的 dict
    """
    result: dict[str, dict[str, object]] = {}
    for uid, pid, overrides in entries:
        key = uid if not pid else f"{uid}__{pid}"
        result[key] = build_record(**overrides)
    return result


def count_sqlite_rows(db_path: str) -> int:
    """返回 SQLite affection 表中的总行数。"""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(CREATE_TABLE_SQL)
        row = conn.execute("SELECT COUNT(*) FROM affection").fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def read_sqlite_all(db_path: str) -> list[dict[str, object]]:
    """以 dict 列表形式返回 SQLite affection 表中全部记录。"""
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute(CREATE_TABLE_SQL)
        rows = conn.execute(
            "SELECT * FROM affection ORDER BY user_id, persona_id"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def read_sqlite_one(db_path: str, user_id: str, persona_id: str = "") -> dict[str, object] | None:
    """按主键查询单条记录。"""
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute(CREATE_TABLE_SQL)
        row = conn.execute(
            "SELECT * FROM affection WHERE user_id=? AND persona_id=?",
            (user_id, persona_id or "default"),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ══════════════════════════════════════════════════════
# 测试类
# ══════════════════════════════════════════════════════

class TestMigration:
    """JSON→SQLite 数据迁移完整测试套件。"""

    # ── 夹具 ────────────────────────────────────────

    @pytest.fixture(autouse=True)
    def _tmpdir(self):
        """每个测试方法在独立的临时目录中执行。"""
        with tempfile.TemporaryDirectory() as td:
            self.tmpdir = Path(td)
            self.json_path = str(self.tmpdir / "relationships.json")
            self.bak_path = str(self.tmpdir / "relationships.json.bak")
            self.db_path = str(self.tmpdir / "affection.db")
            yield

    # ── 辅助方法 ────────────────────────────────────

    def _create_storage(self) -> SQLiteAffectionStorage:
        """创建已就绪的 SQLiteAffectionStorage 实例。"""
        return SQLiteAffectionStorage(self.db_path)

    def _write_json(self, data: dict[str, object]) -> None:
        """向 self.json_path 写入 JSON 文件。"""
        with open(self.json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _assert_record_matches(
        self,
        row: dict[str, object],
        expected: dict[str, object],
    ) -> None:
        """断言单条 SQLite 行与预期的 JSON 记录匹配。"""
        assert row["level"] == pytest.approx(float(expected["level"]), abs=0.5)
        assert row["message_count"] == expected["message_count"]
        assert row["positive_count"] == expected["positive_count"]
        assert row["negative_count"] == expected["negative_count"]
        assert row["last_interaction"] == expected["last_interaction"]
        assert row["created_at"] == expected["created_at"]

    # ── 测试用例 ────────────────────────────────────

    def test_full_migration(self):
        """完整迁移：3 个用户 × 2 个人设 → 验证所有字段。"""
        entries = [
            ("user_a", "p1", {"level": 30.5, "message_count": 10, "positive_count": 5, "negative_count": 1}),
            ("user_a", "p2", {"level": 65.0, "message_count": 22, "positive_count": 8, "negative_count": 3}),
            ("user_b", "p1", {"level": 80.0, "message_count": 45, "positive_count": 20, "negative_count": 0}),
            ("user_b", "p2", {"level": 42.0, "message_count": 7, "positive_count": 2, "negative_count": 2}),
            ("user_c", "p1", {"level": 90.5, "message_count": 99, "positive_count": 60, "negative_count": 5}),
            ("user_c", "p2", {"level": 55.0, "message_count": 14, "positive_count": 6, "negative_count": 1}),
        ]
        data = build_json_data(entries)
        self._write_json(data)

        storage = self._create_storage()
        result = storage.migrate_from_json(self.json_path)

        assert result is True, "完整迁移应返回 True"
        assert count_sqlite_rows(self.db_path) == 6

        rows = read_sqlite_all(self.db_path)
        for row in rows:
            user_id = row["user_id"]
            persona_id = row["persona_id"]
            expected_key = f"{user_id}__{persona_id}"
            assert expected_key in data, f"SQLite 中存在未预期的记录：{expected_key}"
            self._assert_record_matches(row, data[expected_key])

    def test_migration_preserves_level(self):
        """level=72.5 迁移后在 SQLite 中仍为 72.5（±0.5）。"""
        data = build_json_data([
            ("user1", "p1", {"level": 72.5}),
        ])
        self._write_json(data)

        storage = self._create_storage()
        result = storage.migrate_from_json(self.json_path)

        assert result is True
        row = read_sqlite_one(self.db_path, "user1", "p1")
        assert row is not None
        assert row["level"] == pytest.approx(72.5, abs=0.5)

    def test_migration_preserves_counts(self):
        """message_count=150, positive_count=45, negative_count=12 → 精确匹配。"""
        data = build_json_data([
            ("user1", "p1", {
                "message_count": 150,
                "positive_count": 45,
                "negative_count": 12,
            }),
        ])
        self._write_json(data)

        storage = self._create_storage()
        result = storage.migrate_from_json(self.json_path)

        assert result is True
        row = read_sqlite_one(self.db_path, "user1", "p1")
        assert row is not None
        assert row["message_count"] == 150
        assert row["positive_count"] == 45
        assert row["negative_count"] == 12

    def test_migration_preserves_timestamps(self):
        """last_interaction 和 created_at 字符串精确匹配。"""
        data = build_json_data([
            ("user1", "p1", {
                "last_interaction": "2026-06-13T17:17:36.804153",
                "created_at": "2026-06-12T20:01:37.938626",
            }),
        ])
        self._write_json(data)

        storage = self._create_storage()
        result = storage.migrate_from_json(self.json_path)

        assert result is True
        row = read_sqlite_one(self.db_path, "user1", "p1")
        assert row is not None
        assert row["last_interaction"] == "2026-06-13T17:17:36.804153"
        assert row["created_at"] == "2026-06-12T20:01:37.938626"

    def test_json_not_found(self):
        """JSON 文件不存在 → 返回 False，不崩溃。"""
        storage = self._create_storage()
        result = storage.migrate_from_json(
            str(self.tmpdir / "nonexistent.json")
        )
        assert result is False, "文件不存在应返回 False"

    def test_json_corrupted(self):
        """JSON 文件损坏 → 返回 False，不崩溃。"""
        with open(self.json_path, "w", encoding="utf-8") as f:
            f.write("这不是合法的 JSON 内容 ~~~")

        storage = self._create_storage()
        result = storage.migrate_from_json(self.json_path)
        assert result is False, "损坏的 JSON 应返回 False"

    def test_backup_created(self):
        """迁移成功后，relationships.json.bak 存在且内容与原 JSON 一致。"""
        original = build_json_data([
            ("user1", "p1", {"level": 60.0}),
            ("user2", "p1", {"level": 70.0}),
        ])
        self._write_json(original)

        storage = self._create_storage()
        result = storage.migrate_from_json(self.json_path)

        assert result is True
        assert os.path.exists(self.bak_path), ".bak 备份文件应存在"

        with open(self.bak_path, "r", encoding="utf-8") as f:
            bak_content = json.load(f)
        assert bak_content == original, ".bak 内容应与原始 JSON 一致"

    def test_rollback_restores(self):
        """迁移后，可通过 .bak 将原 JSON 完整恢复。"""
        original = build_json_data([
            ("alice", "girlfriend_001", {"level": 55.0}),
            ("bob", "girlfriend_001", {"level": 65.0}),
        ])
        self._write_json(original)

        storage = self._create_storage()
        assert storage.migrate_from_json(self.json_path) is True

        # 确认 .bak 存在
        assert os.path.exists(self.bak_path)

        # 从 .bak 恢复：覆盖原路径
        import shutil
        shutil.copy2(self.bak_path, self.json_path)

        with open(self.json_path, "r", encoding="utf-8") as f:
            restored = json.load(f)
        assert restored == original, "从 .bak 恢复后的 JSON 应与原始数据一致"

    def test_migration_idempotent(self):
        """运行两次迁移，数据不应重复导入。"""
        data = build_json_data([
            ("user1", "p1", {"level": 50.0}),
            ("user1", "p2", {"level": 60.0}),
            ("user2", "p1", {"level": 70.0}),
        ])
        self._write_json(data)

        storage = self._create_storage()

        # 第一次迁移
        result1 = storage.migrate_from_json(self.json_path)
        assert result1 is True
        assert count_sqlite_rows(self.db_path) == 3

        # 第二次迁移（幂等）
        result2 = storage.migrate_from_json(self.json_path)
        assert result2 is True
        assert count_sqlite_rows(self.db_path) == 3, "重复迁移不应增加行数"

        # 验证第二次迁移后 level 值仍是原始值（未被重复累加）
        row = read_sqlite_one(self.db_path, "user1", "p1")
        assert row is not None
        assert row["level"] == pytest.approx(50.0, abs=0.5)

    def test_partial_failure_rollback(self):
        """3 个用户中 1 个数据损坏 → 该用户回滚，其他成功。"""
        entries = [
            ("ok_user1", "p1", {"level": 50.0, "message_count": 10}),
            ("ok_user2", "p1", {"level": 60.0, "message_count": 20}),
            # 第三个用户数据损坏 — level 为不合法类型
        ]
        data = build_json_data(entries)
        # 手动覆盖损坏记录
        data["bad_user__p1"] = {
            "level": "not-a-number",  # 类型错误
            "message_count": 5,
            "positive_count": 0,
            "negative_count": 0,
            "last_interaction": "2026-06-13T00:00:00.000000",
            "created_at": "2026-06-12T00:00:00.000000",
        }
        self._write_json(data)

        storage = self._create_storage()
        result = storage.migrate_from_json(self.json_path)

        # 整体迁移应报告 False（因为存在失败）
        assert result is False

        # 但前两个用户的合法数据应保留
        row1 = read_sqlite_one(self.db_path, "ok_user1", "p1")
        assert row1 is not None, "合法用户的记录应存在"
        assert row1["level"] == pytest.approx(50.0, abs=0.5)

        row2 = read_sqlite_one(self.db_path, "ok_user2", "p1")
        assert row2 is not None, "合法用户的记录应存在"
        assert row2["level"] == pytest.approx(60.0, abs=0.5)

        # 损坏用户的记录不应出现在 SQLite 中
        bad_row = read_sqlite_one(self.db_path, "bad_user", "p1")
        assert bad_row is None, "数据损坏的用户应被回滚，SQLite 中不应有该记录"

    def test_migration_with_empty_json(self):
        """空对象 {} → 迁移返回 True，SQLite 中无数据行。"""
        self._write_json({})

        storage = self._create_storage()
        result = storage.migrate_from_json(self.json_path)

        assert result is True, "空 JSON 迁移应返回 True"
        assert count_sqlite_rows(self.db_path) == 0, "空 JSON 不应产生任何数据行"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
