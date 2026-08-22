"""T13: Legacy web_user.json migration + avatar orphan cleanup tests.

Covers two features:
1. ``migrate_legacy_web_user`` — detects legacy ``data/chat_history/web_user.json``
   + no ``web:default`` binding → creates binding + writes ``.web_user_migrated``
   marker. Idempotent; failure does not crash.
2. ``PersonaLoader.delete`` avatar orphan cleanup — deleting a persona also
   removes ``data/avatars/{persona_id}.*`` files.

隐私: 所有 ID 用占位符 (test_p1, wxid_test)，不含真实账号。
"""

import sys
import json
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


def _make_legacy_db(path: Path, ddl: str, rows: list[tuple]) -> None:
    import sqlite3

    conn = sqlite3.connect(path)
    try:
        conn.execute(ddl)
        table = ddl.split("(", 1)[0].split()[-1]
        placeholders = ",".join("?" for _ in rows[0]) if rows else ""
        if rows:
            conn.executemany(f"INSERT INTO {table} VALUES ({placeholders})", rows)
        conn.commit()
    finally:
        conn.close()


def test_sqlite_legacy_databases_consolidate_and_archive(tmp_path):
    from core.storage.migrations import consolidate_legacy_databases

    _make_legacy_db(
        tmp_path / "memories.db",
        "CREATE TABLE memories (user_id TEXT, id TEXT, content TEXT, PRIMARY KEY(user_id,id))",
        [("user-1", "m-1", "记住我喜欢猫")],
    )
    _make_legacy_db(
        tmp_path / "vectors.db",
        "CREATE TABLE memories (user_id TEXT, memory_id TEXT, content TEXT, embedding BLOB, created_at TEXT, PRIMARY KEY(user_id,memory_id))",
        [("user-1", "m-1", "记住我喜欢猫", b"vector", "now")],
    )

    report = consolidate_legacy_databases(tmp_path)

    assert report.migrated == {"memories.db": 1, "vectors.db": 1}
    assert report.archived_to is not None
    assert (tmp_path / "companion.db").exists()
    assert not (tmp_path / "memories.db").exists()
    assert not (tmp_path / "vectors.db").exists()

    import sqlite3
    conn = sqlite3.connect(tmp_path / "companion.db")
    try:
        assert conn.execute("SELECT content FROM memories").fetchone()[0] == "记住我喜欢猫"
        assert conn.execute("SELECT content FROM memory_vectors").fetchone()[0] == "记住我喜欢猫"
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        conn.close()

    second = consolidate_legacy_databases(tmp_path)
    assert second.migrated == {}


def test_sqlite_consolidation_rolls_back_on_missing_legacy_table(tmp_path):
    from core.storage.migrations import consolidate_legacy_databases

    _make_legacy_db(
        tmp_path / "memories.db",
        "CREATE TABLE wrong_table (value TEXT)",
        [("bad",)],
    )

    with pytest.raises(Exception, match="missing table"):
        consolidate_legacy_databases(tmp_path)
    assert not (tmp_path / "companion.db").exists()
    assert (tmp_path / "memories.db").exists()


def test_domain_stores_share_one_database_and_keep_vector_table_separate(tmp_path):
    from core.emotion.mood import MoodEngine
    from core.memory.storage import MemoryStorage
    from core.memory.vector_store import VectorStore
    from core.memory.identity import IdentityStorage
    from core.memory.life_summary import LifeSummaryStorage
    from core.memory.open_loop import OpenLoopStorage
    from core.memory.layers.long_term import LongTermMemory
    from core.personality.engine import PersonalityEngine
    from core.social.affection.storage import UnifiedAffectionStorage
    from core.social.relationship.events import RelationshipEventStorage
    from core.storage.db import get_db_path

    MemoryStorage(tmp_path)
    VectorStore(get_db_path(tmp_path))
    MoodEngine(tmp_path)
    PersonalityEngine(tmp_path)
    UnifiedAffectionStorage(tmp_path)
    IdentityStorage(tmp_path)
    OpenLoopStorage(tmp_path)
    LifeSummaryStorage(tmp_path)
    RelationshipEventStorage(tmp_path)
    LongTermMemory(tmp_path)

    import sqlite3
    conn = sqlite3.connect(get_db_path(tmp_path))
    try:
        tables = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    finally:
        conn.close()
    assert {
        "memories", "memory_vectors", "moods", "personalities", "affection",
        "identity", "open_loops", "life_summaries", "relationship_events", "facts",
    } <= tables


def test_consolidated_database_supports_concurrent_writers(tmp_path):
    import sqlite3
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from core.storage.db import get_db_path, open_db

    db_path = get_db_path(tmp_path)
    conn = open_db(db_path)
    conn.execute(
        "CREATE TABLE concurrency_probe (id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
    )
    conn.commit()
    conn.close()

    worker_count = 10
    barrier = threading.Barrier(worker_count)

    def write_row(index: int) -> None:
        worker_conn = open_db(db_path)
        try:
            barrier.wait(timeout=5)
            worker_conn.execute(
                "INSERT INTO concurrency_probe(id, value) VALUES (?, ?)",
                (index, f"value-{index}"),
            )
            worker_conn.commit()
        finally:
            worker_conn.close()

    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        list(pool.map(write_row, range(worker_count)))

    check = sqlite3.connect(db_path)
    try:
        assert check.execute("SELECT COUNT(*) FROM concurrency_probe").fetchone()[0] == worker_count
        assert check.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        check.close()

from core.conversation.store import ConversationStore
from core.persona.loader import PersonaLoader
from core.persona.models import Persona
from core.config import DEFAULT_PERSONA_ID

import webui.server as srv


# ════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════

def _make_legacy_web_user_json(tmp_path: Path, messages: list[dict] | None = None) -> Path:
    """Create a fake legacy ``data/chat_history/web_user.json`` with messages."""
    chat_dir = tmp_path / "chat_history"
    chat_dir.mkdir(parents=True, exist_ok=True)
    legacy_file = chat_dir / "web_user.json"
    data = {"messages": messages or [], "short_memories": []}
    legacy_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return legacy_file


def _make_store(tmp_path: Path) -> ConversationStore:
    """Create a ConversationStore pointing at tmp_path/conversations.json."""
    return ConversationStore(file_path=tmp_path / "conversations.json")


def _make_persona_loader(tmp_path: Path) -> PersonaLoader:
    """Create a PersonaLoader with an empty personas.json in tmp_path."""
    config_path = tmp_path / "personas.json"
    config_path.write_text('{"personas": []}', encoding="utf-8")
    return PersonaLoader(str(config_path))


# ════════════════════════════════════════════════════════════════
# Migration tests
# ════════════════════════════════════════════════════════════════

def test_migration_creates_binding_when_web_user_json_exists(tmp_path):
    """Given: web_user.json exists + no binding + no marker.
    When:  migrate runs.
    Then:  web:default binding created with DEFAULT_PERSONA_ID + marker written.
    """
    _make_legacy_web_user_json(tmp_path, [{"role": "user", "content": "hi"}])
    store = _make_store(tmp_path)

    srv.migrate_legacy_web_user(store, tmp_path)

    binding = store.find("web", "", "default")
    assert binding is not None
    assert binding.platform == "web"
    assert binding.account_id == ""
    assert binding.contact_id == "default"
    assert binding.persona_id == DEFAULT_PERSONA_ID
    assert (tmp_path / ".web_user_migrated").exists()


def test_migration_skips_when_marker_exists(tmp_path):
    """Given: marker pre-exists + web_user.json exists + no binding.
    When:  migrate runs.
    Then:  no-op — no binding created (marker is the idempotency gate).
    """
    (tmp_path / ".web_user_migrated").touch()
    _make_legacy_web_user_json(tmp_path)
    store = _make_store(tmp_path)

    srv.migrate_legacy_web_user(store, tmp_path)

    assert store.find("web", "", "default") is None
    assert len(store.list()) == 0


def test_migration_skips_when_web_user_json_missing(tmp_path):
    """Given: no web_user.json + no binding + no marker.
    When:  migrate runs.
    Then:  no binding created, but marker written (prevent future checks).
    """
    store = _make_store(tmp_path)

    srv.migrate_legacy_web_user(store, tmp_path)

    assert store.find("web", "", "default") is None
    assert (tmp_path / ".web_user_migrated").exists()


def test_migration_skips_when_binding_already_exists(tmp_path):
    """Given: web:default binding pre-exists (manual create) + no marker.
    When:  migrate runs.
    Then:  no duplicate binding created, marker written (self-heal).
    """
    _make_legacy_web_user_json(tmp_path)
    store = _make_store(tmp_path)
    # Pre-create the binding manually (simulates user creating it via API)
    store.create(
        platform="web", account_id="", contact_id="default",
        persona_id=DEFAULT_PERSONA_ID,
    )

    srv.migrate_legacy_web_user(store, tmp_path)

    # Still exactly 1 binding — no duplicate
    bindings = store.list()
    assert len(bindings) == 1
    assert bindings[0].contact_id == "default"
    # Marker self-heal
    assert (tmp_path / ".web_user_migrated").exists()


def test_migration_idempotent_run_twice(tmp_path):
    """Given: web_user.json exists + no binding + no marker.
    When:  migrate runs twice.
    Then:  exactly 1 binding created; second run is a no-op (marker gates it).
    """
    _make_legacy_web_user_json(tmp_path)
    store = _make_store(tmp_path)

    srv.migrate_legacy_web_user(store, tmp_path)
    srv.migrate_legacy_web_user(store, tmp_path)

    bindings = store.list()
    assert len(bindings) == 1
    assert bindings[0].platform == "web"
    assert bindings[0].contact_id == "default"
    assert bindings[0].persona_id == DEFAULT_PERSONA_ID


def test_migration_failure_does_not_crash(tmp_path):
    """Given: web_user.json exists + store.create raises RuntimeError.
    When:  migrate runs.
    Then:  warning logged, no exception propagated (server startup safe).
    """
    _make_legacy_web_user_json(tmp_path)
    store = _make_store(tmp_path)
    # Mock create to raise a non-ValueError exception (real failure, not race)
    store.create = MagicMock(side_effect=RuntimeError("simulated failure"))

    # Must not raise — this is the critical "migration must not crash server" guarantee
    srv.migrate_legacy_web_user(store, tmp_path)

    # create was attempted (find returned None, legacy file exists)
    store.create.assert_called_once()


# ════════════════════════════════════════════════════════════════
# Avatar orphan cleanup tests (PersonaLoader.delete)
# ════════════════════════════════════════════════════════════════

def test_persona_delete_cleans_avatar_files(tmp_path, monkeypatch):
    """Given: persona exists + avatar file at avatars/{id}.png.
    When:  PersonaLoader.delete(persona_id).
    Then:  persona removed from personas.json + avatar file unlinked.
    """
    from core.persona import loader as loader_mod
    avatar_dir = tmp_path / "avatars"
    avatar_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(loader_mod, "_AVATAR_DIR", avatar_dir)

    loader = _make_persona_loader(tmp_path)
    loader.add(Persona(id="test_p1", name="测试"))
    avatar_file = avatar_dir / "test_p1.png"
    avatar_file.write_bytes(b"fake png bytes")
    assert avatar_file.exists()

    result = loader.delete("test_p1")

    assert result is True
    assert not avatar_file.exists()
    # Persona also removed from loader
    assert loader.get("test_p1") is None


def test_persona_delete_no_avatar_silent(tmp_path, monkeypatch):
    """Given: persona exists + no avatar file.
    When:  PersonaLoader.delete(persona_id).
    Then:  persona removed, no error raised (glob matches nothing, silent).
    """
    from core.persona import loader as loader_mod
    avatar_dir = tmp_path / "avatars"
    avatar_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(loader_mod, "_AVATAR_DIR", avatar_dir)

    loader = _make_persona_loader(tmp_path)
    loader.add(Persona(id="test_p2", name="测试"))

    # No avatar file — must not raise
    result = loader.delete("test_p2")

    assert result is True
    assert loader.get("test_p2") is None


def test_persona_delete_multiple_avatar_extensions(tmp_path, monkeypatch):
    """Given: persona exists + avatar files with .png AND .jpg extensions.
    When:  PersonaLoader.delete(persona_id).
    Then:  both avatar files removed (glob matches all extensions).
    """
    from core.persona import loader as loader_mod
    avatar_dir = tmp_path / "avatars"
    avatar_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(loader_mod, "_AVATAR_DIR", avatar_dir)

    loader = _make_persona_loader(tmp_path)
    loader.add(Persona(id="test_p3", name="测试"))
    png_file = avatar_dir / "test_p3.png"
    jpg_file = avatar_dir / "test_p3.jpg"
    png_file.write_bytes(b"fake png")
    jpg_file.write_bytes(b"fake jpg")
    assert png_file.exists()
    assert jpg_file.exists()

    result = loader.delete("test_p3")

    assert result is True
    assert not png_file.exists()
    assert not jpg_file.exists()
