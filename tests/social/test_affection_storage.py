"""亲密度存储单元测试 — UnifiedAffectionStorage 接口规约

这些测试在 Task 9 实现 UnifiedAffectionStorage 之前预期全部失败（RED）。
当具体实现完成后，所有测试应通过（GREEN）。
"""

import sys
import json
import sqlite3
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from core.social.affection.schema import (
    AffectionRecord,
    AffectionStats,
    CREATE_TABLE_SQL,
    AffectionStorage,
)
from core.social.affection.constants import (
    AffectionDirection,
    AffectionLevel,
    DIRECTION_LEVEL_MAP,
    BASE_BONUS,
    MIN_AFFECTION,
    MAX_AFFECTION,
)

# UnifiedAffectionStorage 将在 Task 9 实现
from core.social.affection.schema import UnifiedAffectionStorage


class TestAffectionStorage:
    """UnifiedAffectionStorage 接口规约测试

    所有测试使用 :memory: SQLite 数据库，不写任何磁盘文件（migration 测试除外）。
    """

    # ── Fixtures ──────────────────────────────────────────────

    @pytest.fixture
    def conn(self):
        """内存 SQLite 连接，使用 CREATE_TABLE_SQL 初始化表结构"""
        conn = sqlite3.connect(":memory:")
        conn.execute(CREATE_TABLE_SQL)
        conn.commit()
        yield conn
        conn.close()

    @pytest.fixture
    def storage(self, conn):
        """UnifiedAffectionStorage 实例，绑定到内存数据库"""
        return UnifiedAffectionStorage(conn)

    # ── 基础功能 ─────────────────────────────────────────────

    def test_init_default_level(self, storage):
        """Get level for new user, expect 50"""
        level = storage.get_level("new_user")
        assert level == 50

    def test_update_increases_level(self, storage):
        """Update with positive direction, expect level > 50"""
        storage.update("user1", AffectionDirection.POSITIVE, AffectionLevel.HIGH)
        level = storage.get_level("user1")
        assert level > 50

    def test_update_decreases_level(self, storage):
        """Update with negative direction, expect level < 50"""
        storage.update("user1", AffectionDirection.NEGATIVE, AffectionLevel.HIGH)
        level = storage.get_level("user1")
        assert level < 50

    def test_base_bonus_always_applied(self, storage):
        """Update with NEUTRAL, expect level = 50 + BASE_BONUS (0.02)

        NEUTRAL 方向在 DIRECTION_LEVEL_MAP 中增量为 0，
        但每次更新都应叠加 BASE_BONUS，所以结果应为 50.02。
        """
        storage.update("user1", AffectionDirection.NEUTRAL, AffectionLevel.HIGH)
        level = storage.get_level("user1")
        assert level == 50.0 + BASE_BONUS

    # ── 边界值 ───────────────────────────────────────────────

    def test_clamp_max(self, storage):
        """Start at 50, add strong_positive/high repeatedly, verify diminishing returns

        The storage applies diminishing returns as level approaches 100,
        so after 10 iterations the level approaches but does not reach 100.
        With enough iterations the 0.02 floor multiplier ensures it eventually
        reaches exactly 100 (SQL-level clamp).
        """
        for _ in range(10):
            storage.update("user1", AffectionDirection.STRONG_POSITIVE, AffectionLevel.HIGH)
        level = storage.get_level("user1")
        # Diminishing returns: level should be close to 100 but not exceed it
        assert 90 <= level < 100, f"Expected ~98.6 after 10 iterations, got {level}"

        # With enough iterations, the floor multiplier ensures it reaches 100
        for _ in range(20):
            storage.update("user1", AffectionDirection.STRONG_POSITIVE, AffectionLevel.HIGH)
        level = storage.get_level("user1")
        assert level == MAX_AFFECTION, f"Expected clamp to {MAX_AFFECTION}, got {level}"

    def test_clamp_min(self, storage):
        """Start at 50, add strong_negative/high repeatedly, expect clamped to 0

        50 + 10 × (-15.0 + 0.02) = -99.8 → clamped to MIN_AFFECTION (0)
        """
        for _ in range(10):
            storage.update("user1", AffectionDirection.STRONG_NEGATIVE, AffectionLevel.HIGH)
        level = storage.get_level("user1")
        assert level == MIN_AFFECTION

    # ── 隔离性 ───────────────────────────────────────────────

    def test_multi_user_isolation(self, storage):
        """Two users with different updates, verify independent levels"""
        storage.update("alice", AffectionDirection.POSITIVE, AffectionLevel.HIGH)
        storage.update("bob", AffectionDirection.NEGATIVE, AffectionLevel.HIGH)
        alice_level = storage.get_level("alice")
        bob_level = storage.get_level("bob")
        assert alice_level > 50
        assert bob_level < 50

    def test_multi_persona_isolation(self, storage):
        """Same user, two persona_ids, verify independent levels"""
        storage.update("user1", AffectionDirection.POSITIVE, AffectionLevel.HIGH, persona_id="waifu")
        storage.update("user1", AffectionDirection.NEGATIVE, AffectionLevel.HIGH, persona_id="tsundere")
        waifu_level = storage.get_level("user1", persona_id="waifu")
        tsundere_level = storage.get_level("user1", persona_id="tsundere")
        assert waifu_level > 50
        assert tsundere_level < 50

    # ── 统计与元数据 ─────────────────────────────────────────

    def test_get_stats_format(self, storage):
        """After update, stats dict / AffectionStats has all expected fields"""
        storage.update("user1", AffectionDirection.POSITIVE, AffectionLevel.HIGH)
        storage.update("user1", AffectionDirection.POSITIVE, AffectionLevel.MEDIUM)
        storage.update("user1", AffectionDirection.NEGATIVE, AffectionLevel.LOW)
        stats = storage.get_stats("user1")
        assert isinstance(stats, AffectionStats)
        assert isinstance(stats.level, float)
        assert isinstance(stats.message_count, int)
        assert isinstance(stats.positive_count, int)
        assert isinstance(stats.negative_count, int)
        assert isinstance(stats.days_known, int)
        assert stats.message_count == 3
        assert stats.positive_count == 2
        assert stats.negative_count == 1

    def test_get_last_interaction(self, storage):
        """After update, last_interaction should be non-empty string"""
        storage.update("user1", AffectionDirection.NEUTRAL, AffectionLevel.LOW)
        ts = storage.get_last_interaction("user1")
        assert ts is not None
        assert isinstance(ts, str)
        assert len(ts) > 0

    # ── 衰减 ─────────────────────────────────────────────────

    def test_apply_decay(self, storage, conn):
        """Older than 3 days, verify level drops"""
        # 先提高亲密度作为衰减的基准
        storage.update("user1", AffectionDirection.POSITIVE, AffectionLevel.HIGH)
        storage.update("user1", AffectionDirection.STRONG_POSITIVE, AffectionLevel.HIGH)
        level_before = storage.get_level("user1")

        # 模拟 last_interaction 为 4 天前（直接操作 SQLite）
        old_ts = (datetime.now() - timedelta(days=4)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "UPDATE affection SET last_interaction = ? WHERE user_id = ? AND persona_id = ?",
            (old_ts, "user1", "default"),
        )
        conn.commit()

        # 应用衰减后亲密度应降低
        level_after = storage.apply_decay("user1")
        assert level_after < level_before

    # ── 迁移 ─────────────────────────────────────────────────

    def test_migrate_from_json(self, storage):
        """Create temp JSON, run migration, verify SQLite matches"""
        json_data = {
            "user_alpha": {
                "default": {
                    "level": 72.5,
                    "message_count": 15,
                    "positive_count": 10,
                    "negative_count": 2,
                    "last_interaction": "2026-06-10 12:00:00",
                    "created_at": "2026-06-01 08:00:00",
                },
            },
            "user_beta": {
                "default": {
                    "level": 30.0,
                    "message_count": 8,
                    "positive_count": 3,
                    "negative_count": 4,
                    "last_interaction": "2026-06-11 14:30:00",
                    "created_at": "2026-06-05 10:00:00",
                },
            },
        }

        f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        try:
            json.dump(json_data, f)
            f.close()

            result = storage.migrate_from_json(f.name)
            assert result is True

            # 验证 SQLite 中数据与 JSON 一致
            alpha_level = storage.get_level("user_alpha")
            assert alpha_level == 72.5

            beta_level = storage.get_level("user_beta")
            assert beta_level == 30.0

            alpha_stats = storage.get_stats("user_alpha")
            assert alpha_stats.message_count == 15
            assert alpha_stats.positive_count == 10
            assert alpha_stats.negative_count == 2
        finally:
            Path(f.name).unlink(missing_ok=True)
