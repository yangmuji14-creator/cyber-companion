"""WebUI server route tests — comprehensive pytest suite for all webui/server.py routes.

Mocks AppComponents so NO real LLM/database is needed.
Uses aiohttp TestClient for HTTP-level testing.
asyncio_mode=auto handles async tests (no @pytest.mark.asyncio needed).
"""

import sys
import json
import types
import io
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import aiohttp
import pytest
from aiohttp.test_utils import TestClient, TestServer

import webui.server as srv
from core.config import build_web_uid
from core.persona.models import Persona
from core.memory.models import Memory
from core.security.secrets import SecretManager


# ════════════════════════════════════════════════════════════════
# Fakes — provide the minimum interface server.py accesses
# ════════════════════════════════════════════════════════════════

class FakePipeline:
    """Fake ChatPipeline — records calls, returns canned reply, emits tokens."""

    def __init__(self):
        self.calls = []
        self.reply = "测试回复"
        self.level = 50
        self.tokens = ["你", "好"]

    async def process(self, user_id, content, persona_id,
                      on_token=None, skip_user_message=False, scope_id=None):
        self.calls.append({
            "user_id": user_id,
            "content": content,
            "persona_id": persona_id,
            "skip_user_message": skip_user_message,
            "scope_id": scope_id,
        })
        if on_token:
            for t in self.tokens:
                on_token(t)
        return self.reply, self.level


class FakeHandler:
    def __init__(self, pipeline):
        self.pipeline = pipeline


class FakeChatHistory:
    def __init__(self):
        self.messages = []
        self.deleted_users = []  # 记录被 delete_user 调用过的 user_id

    def get_messages(self, user_id):
        return [dict(m) for m in self.messages]

    def delete_last_messages(self, user_id, count=2):
        if not self.messages:
            return []
        n = min(count, len(self.messages))
        deleted = self.messages[-n:]
        self.messages = self.messages[:-n]
        return deleted

    def delete_user(self, user_id):
        """模拟清空用户聊天历史。记录调用以便测试断言。"""
        self.deleted_users.append(user_id)
        self.messages = []
        return True

    def add_test_message(self, role="user", content="测试消息"):
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": "2025-01-01T00:00:00",
        })


class FakePersonaLoader:
    USER_FIELDS = {"name", "age", "gender", "hometown", "personality", "mbti"}
    ADVANCED_FIELDS = {
        "system_prompt", "persona_prompt", "output_examples",
        "hard_rules", "identity_anchor",
    }
    ALLOWED_FIELDS = USER_FIELDS | ADVANCED_FIELDS | {"avatar"}

    def __init__(self):
        self._personas = {}

    def list_all(self):
        return list(self._personas.values())

    def get(self, persona_id):
        return self._personas.get(persona_id)

    def update(self, persona_id, **kwargs):
        p = self._personas.get(persona_id)
        if not p:
            return None
        for k, v in kwargs.items():
            if k in self.ALLOWED_FIELDS:
                setattr(p, k, v)
        return p

    def add_test_persona(self, pid="test_001", name="测试人设"):
        p = Persona(id=pid, name=name)
        self._personas[pid] = p
        return p


class FakeRegistry:
    """Empty registry — _apply_live skips LLM attribute updates."""

    def __init__(self):
        self.available_models = []


class FakeMemoryMgr:
    """Fake MemoryManager — backs /api/memory list + detail routes."""

    def __init__(self):
        self._memories: dict[str, Memory] = {}

    def get_memories(self, user_id, level_min=1, level_max=5, limit=999):
        filtered = [m for m in self._memories.values()
                    if level_min <= m.level <= level_max]
        filtered.sort(key=lambda m: (m.level, m.last_accessed), reverse=True)
        return filtered[:limit]

    def get_memory(self, user_id, memory_id):
        return self._memories.get(memory_id)

    def add_test_memory(self, mid, content="测试记忆", level=1, category="other",
                        created_at="2025-01-01T00:00:00",
                        last_accessed="2025-01-01T00:00:00",
                        access_count=0, tags=None, related_memory_ids=None,
                        superseded_by="", source="auto", confidence=0.5,
                        forget_score=0.0, archived=False):
        m = Memory(
            id=mid, content=content, level=level, category=category,
            created_at=created_at, last_accessed=last_accessed,
            access_count=access_count, tags=tags or [],
            related_memory_ids=related_memory_ids or [],
            superseded_by=superseded_by, source=source,
            confidence=confidence, forget_score=forget_score,
            archived=archived,
        )
        self._memories[mid] = m
        return m


class FakeLifeSummaryStorage:
    """Fake LifeSummaryStorage — backs /api/life_summary routes."""

    def __init__(self):
        self._summaries: list = []

    def load_by_user(self, user_id, limit=10, persona_id=""):
        return list(self._summaries[:limit])

    def load_latest(self, user_id, persona_id=""):
        return self._summaries[0] if self._summaries else None

    def add_test_summary(self, sid="ls1", summary_type="daily",
                         summary="测试摘要", recent_status="状态良好",
                         key_events=None, message_count=10,
                         created_at="2025-01-01T00:00:00",
                         emotional_trends="平稳"):
        s = types.SimpleNamespace(
            id=sid, summary_type=summary_type, summary=summary,
            recent_status=recent_status, key_events=key_events or [],
            message_count=message_count, created_at=created_at,
            emotional_trends=emotional_trends,
        )
        self._summaries.append(s)
        return s


class FakeLifeSummaryEngine:
    """Fake LifeSummaryEngine — exposes _sqlite_storage attribute."""

    def __init__(self):
        self._sqlite_storage = FakeLifeSummaryStorage()


class FakeAppComponents:
    def __init__(self):
        self.pipeline = FakePipeline()
        self.handler = FakeHandler(self.pipeline)
        self.chat_history = FakeChatHistory()
        self.persona_loader = FakePersonaLoader()
        # Lazy-init: tests that hit /api/conversations set this to a real
        # ConversationStore pointing at tmp_path. Default None so existing
        # tests that don't touch conversations routes stay unaffected.
        self.conversation_store = None
        self.registry = FakeRegistry()
        self.advanced_config = {}
        self.proactive = None
        self.vision_manager = None
        self.memory_mgr = FakeMemoryMgr()
        self.life_summary = FakeLifeSummaryEngine()
        # 与 AppComponents 字段对齐：默认 None，需要 wechat 路由的测试按需注入
        self.adapter_manager = None


class FakeSecretBackend:
    name = "test-secure-store"
    available = True

    def __init__(self):
        self.values = {}

    def get(self, reference):
        return self.values.get(reference, "")

    def set(self, reference, value):
        self.values[reference] = value

    def delete(self, reference):
        self.values.pop(reference, None)


# ════════════════════════════════════════════════════════════════
# Fixture — patched settings + faked components + TestClient
# ════════════════════════════════════════════════════════════════

@pytest.fixture
async def api(monkeypatch, tmp_path):
    """Yield (TestClient, FakeAppComponents) with patched settings paths."""
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({
        "default_model": "test-model",
        "models": {"test-model": {"temperature": 1.0, "max_tokens": 4096}},
        "advanced": {"segment_max_length": 16},
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(srv, "SETTINGS_PATH", settings_file)

    monkeypatch.setattr(srv, "load_advanced", lambda: {
        "segment_max_length": 16, "debounce_seconds": 3,
        "summarize_threshold": 15, "max_retries": 2,
        "proactive_enabled": True, "auto_extract_memory": False,
    })

    monkeypatch.setattr(srv, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(srv, "AVATAR_DIR", tmp_path / "avatars")
    monkeypatch.setattr(srv, "DATA_DIR", tmp_path / "data")
    secret_manager = SecretManager(FakeSecretBackend())
    monkeypatch.setattr(srv, "_secret_manager", lambda: secret_manager)

    components = FakeAppComponents()
    components.persona_loader.add_test_persona("test_001", "测试人设")
    components.persona_loader.add_test_persona("test_002", "另一个")

    app = srv._make_app(components)
    server = TestServer(app)
    cli = TestClient(server)
    await cli.start_server()
    try:
        yield cli, components
    finally:
        await cli.close()


# ════════════════════════════════════════════════════════════════
# Tests: original routes
# ════════════════════════════════════════════════════════════════

async def test_index_get(api):
    """GET / — serves index.html (200) or 404 if missing."""
    client, _ = api
    resp = await client.get("/")
    assert resp.status in (200, 404)


async def test_get_schema(api):
    """GET /api/schema — returns schema list with field definitions."""
    client, _ = api
    resp = await client.get("/api/schema")
    assert resp.status == 200
    data = await resp.json()
    assert "schema" in data
    assert isinstance(data["schema"], list)
    assert len(data["schema"]) > 0
    first = data["schema"][0]
    assert "key" in first
    assert "label" in first
    assert "type" in first


async def test_get_health(api):
    client, _ = api
    resp = await client.get("/api/health")
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    assert "runtime" in data
    assert "uptime_seconds" in data["runtime"]


async def test_diagnostics_and_export_are_sanitized(api):
    client, _components = api
    settings = srv._load_settings()
    settings["models"]["test-model"]["api_key"] = "do-not-export"
    srv._save_settings(settings)

    response = await client.get("/api/diagnostics")
    assert response.status == 200
    report = await response.json()
    assert {item["id"] for item in report["checks"]} >= {
        "platform", "database", "model", "vision", "secrets",
    }
    assert "do-not-export" not in json.dumps(report)

    exported = await client.get("/api/diagnostics/export")
    assert exported.status == 200
    payload = await exported.read()
    assert b"do-not-export" not in payload
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        assert set(archive.namelist()) == {"diagnostics.json", "settings.sanitized.json"}
        sanitized = archive.read("settings.sanitized.json").decode("utf-8")
        assert "do-not-export" not in sanitized
        assert "[已配置]" in sanitized


async def test_bootstrap_status_and_provider_catalog(api):
    client, _ = api
    status = await client.get("/api/bootstrap/status")
    assert status.status == 200
    status_data = await status.json()
    assert status_data["needs_setup"] is True

    providers = await client.get("/api/bootstrap/providers")
    assert providers.status == 200
    data = await providers.json()
    assert {item["key"] for item in data["providers"]} >= {"deepseek", "qwen", "openai"}
    assert all("api_key" not in item for item in data["providers"])


async def test_bootstrap_complete_persists_model(api):
    client, _ = api
    response = await client.post("/api/bootstrap/complete", json={
        "provider": "deepseek",
        "api_key": "sk-test",
        "model_name": "deepseek-chat",
        "base_url": "https://api.deepseek.com/v1",
    })
    assert response.status == 200
    data = await response.json()
    assert data["ok"] is True
    saved = json.loads(srv.SETTINGS_PATH.read_text(encoding="utf-8"))
    assert saved["default_model"] == "deepseek"
    assert saved["models"]["deepseek"]["model_name"] == "deepseek-chat"


async def test_bootstrap_model_discovery_uses_backend(api, monkeypatch):
    client, _ = api

    async def fake_discover(**kwargs):
        assert kwargs["base_url"] == "https://example.test/v1"
        assert kwargs["api_key"] == "secret"
        return {"ok": True, "models": ["model-a", "model-b"], "message": "已找到 2 个模型"}

    monkeypatch.setattr(srv, "discover_models", fake_discover)
    response = await client.post("/api/bootstrap/models", json={
        "base_url": "https://example.test/v1", "api_key": "secret",
    })
    assert response.status == 200
    assert (await response.json())["models"] == ["model-a", "model-b"]


async def test_bootstrap_persona_saves_three_core_fields(api):
    client, components = api
    components.persona_loader.add_test_persona(srv.DEFAULT_PERSONA_ID, "默认人设")
    response = await client.post("/api/bootstrap/persona", json={
        "system_prompt": "稳定规则",
        "output_examples": "你说：早呀",
        "persona_prompt": "你叫小雨，喜欢散步。",
    })
    assert response.status == 200
    persona = components.persona_loader.get(srv.DEFAULT_PERSONA_ID)
    assert persona.system_prompt == "稳定规则"
    assert persona.output_examples == "你说：早呀"
    assert persona.persona_prompt == "你叫小雨，喜欢散步。"
    saved = json.loads(srv.SETTINGS_PATH.read_text(encoding="utf-8"))
    assert saved["advanced"]["persona_onboarding_completed"] is True


async def test_get_settings(api):
    """GET /api/settings — returns current values dict."""
    client, _ = api
    resp = await client.get("/api/settings")
    assert resp.status == 200
    data = await resp.json()
    assert "values" in data
    assert isinstance(data["values"], dict)


async def test_get_about(api):
    """GET /api/about exposes user-facing local storage and privacy information."""
    client, _ = api
    resp = await client.get("/api/about")
    assert resp.status == 200
    data = await resp.json()
    assert data["name"] == "慕"
    assert data["tagline"].startswith("慕，只是你夜航时偶遇的浮灯")
    assert data["backup_format_version"] >= 1
    assert "本机" in data["privacy"]


async def test_backup_creates_portable_archive(api, monkeypatch, tmp_path):
    """POST /api/backup includes a manifest and transaction-safe SQLite snapshot."""
    client, _ = api
    data_dir = tmp_path / "data"
    config_dir = tmp_path / "config"
    data_dir.mkdir()
    config_dir.mkdir()
    sqlite_file = data_dir / "memories.db"
    import sqlite3
    with sqlite3.connect(sqlite_file) as conn:
        conn.execute("CREATE TABLE sample (value TEXT)")
        conn.execute("INSERT INTO sample VALUES ('kept')")
    (data_dir / "conversations.json").write_text("{}", encoding="utf-8")
    (config_dir / "personas.json").write_text('{"personas": []}', encoding="utf-8")
    (data_dir / "credentials").mkdir()
    (data_dir / "credentials" / "wechat.json").write_text("secret", encoding="utf-8")
    monkeypatch.setattr(srv, "DATA_DIR", data_dir)
    monkeypatch.setattr(srv, "CONFIG_DIR", config_dir)

    resp = await client.post("/api/backup")

    assert resp.status == 200
    archive = zipfile.ZipFile(io.BytesIO(await resp.read()))
    assert {"manifest.json", "data/memories.db", "data/conversations.json", "config/personas.json"} <= set(archive.namelist())
    assert not any("credentials" in path for path in archive.namelist())


async def test_restore_upload_is_queued_until_restart(api, monkeypatch, tmp_path):
    client, _ = api
    data_dir = tmp_path / "restore-data"
    config_dir = tmp_path / "restore-config"
    data_dir.mkdir()
    config_dir.mkdir()
    (data_dir / "conversations.json").write_text("{}", encoding="utf-8")
    archive_path = srv.create_backup(data_dir, config_dir)
    archive_bytes = archive_path.read_bytes()
    monkeypatch.setattr(srv, "DATA_DIR", data_dir)
    monkeypatch.setattr(srv, "CONFIG_DIR", config_dir)

    inspect_form = aiohttp.FormData()
    inspect_form.add_field(
        "backup", archive_bytes, filename="backup.zip", content_type="application/zip",
    )
    inspected = await client.post("/api/backup/inspect", data=inspect_form)
    assert inspected.status == 200

    restore_form = aiohttp.FormData()
    restore_form.add_field(
        "backup", archive_bytes, filename="backup.zip", content_type="application/zip",
    )
    queued = await client.post("/api/restore", data=restore_form)
    assert queued.status == 200
    queued_data = await queued.json()
    assert queued_data["restart_required"] is True

    status = await client.get("/api/restore/status")
    status_data = await status.json()
    assert status_data["pending"] is True


async def test_post_settings_valid(api):
    """POST /api/settings — valid temperature update succeeds."""
    client, _ = api
    resp = await client.post("/api/settings", json={"values": {"temperature": 0.8}})
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True


async def test_post_settings_no_valid_fields(api):
    """POST /api/settings — unknown field returns 400."""
    client, _ = api
    resp = await client.post("/api/settings", json={"values": {"nonexistent_field": 123}})
    assert resp.status == 400


async def test_post_settings_invalid_json(api):
    """POST /api/settings — invalid JSON returns 400."""
    client, _ = api
    resp = await client.post(
        "/api/settings",
        data="not json",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status == 400


async def test_post_settings_method_not_allowed(api):
    """DELETE /api/settings — wrong method returns 405."""
    client, _ = api
    resp = await client.delete("/api/settings")
    assert resp.status == 405


# ════════════════════════════════════════════════════════════════
# Tests: /api/model (new)
# ════════════════════════════════════════════════════════════════

async def test_get_model(api):
    """GET /api/model — returns current model + available list."""
    client, _ = api
    resp = await client.get("/api/model")
    assert resp.status == 200
    data = await resp.json()
    assert "current" in data
    assert "available" in data
    assert isinstance(data["available"], list)
    assert "test-model" in data["available"]


async def test_post_model_valid(api):
    """POST /api/model — switch to a valid model."""
    client, _ = api
    resp = await client.post("/api/model", json={"model": "test-model"})
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    assert data["current"] == "test-model"


async def test_post_model_missing(api):
    """POST /api/model — missing model field returns 400."""
    client, _ = api
    resp = await client.post("/api/model", json={})
    assert resp.status == 400


async def test_post_model_unknown(api):
    """POST /api/model — unknown model returns 400."""
    client, _ = api
    resp = await client.post("/api/model", json={"model": "nonexistent"})
    assert resp.status == 400


async def test_post_model_invalid_json(api):
    """POST /api/model — invalid JSON returns 400."""
    client, _ = api
    resp = await client.post(
        "/api/model",
        data="bad",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status == 400


async def test_get_vision_config_does_not_expose_api_key(api):
    client, components = api
    settings = srv._load_settings()
    settings.setdefault("advanced", {})["vision_model"] = {
        "provider": "openai",
        "model_name": "gpt-4o-mini",
        "base_url": "https://vision.example/v1",
        "api_key": "secret-vision-key",
    }
    srv._save_settings(settings)
    components.vision_manager = types.SimpleNamespace(main_is_multimodal=False)

    resp = await client.get("/api/vision/config")

    assert resp.status == 200
    data = await resp.json()
    assert data["has_api_key"] is True
    assert "api_key" not in data
    assert "secret-vision-key" not in json.dumps(data)


async def test_post_vision_config_preserves_secret_and_applies_live(api):
    client, components = api
    settings = srv._load_settings()
    settings.setdefault("advanced", {})["vision_model"] = {
        "provider": "openai",
        "model_name": "old-vision",
        "base_url": "https://old.example/v1",
        "api_key": "keep-me",
    }
    srv._save_settings(settings)

    class FakeVision:
        main_is_multimodal = False

        def __init__(self):
            self.applied = None

        def update_config(self, config):
            self.applied = dict(config)

    components.vision_manager = FakeVision()
    resp = await client.post("/api/vision/config", json={
        "provider": "openai",
        "model_name": "new-vision",
        "base_url": "",
        "api_key": "",
    })

    assert resp.status == 200
    saved = srv._load_settings()["advanced"]["vision_model"]
    assert saved["api_key"] == ""
    assert saved["api_key_ref"] == "vision/default"
    assert srv.resolve_config_secret(saved, manager=srv._secret_manager()) == "keep-me"
    assert saved["base_url"] == ""
    assert components.vision_manager.applied == {
        "provider": "openai",
        "model_name": "new-vision",
        "base_url": "",
        "api_key": "keep-me",
    }


async def test_post_vision_config_empty_model_disables_fallback(api):
    client, components = api

    class FakeVision:
        main_is_multimodal = False

        def __init__(self):
            self.applied = None

        def update_config(self, config):
            self.applied = dict(config)

    components.vision_manager = FakeVision()
    resp = await client.post("/api/vision/config", json={
        "provider": "openai", "model_name": "", "base_url": "", "api_key": "",
    })

    assert resp.status == 200
    assert components.vision_manager.applied["model_name"] == ""


# ════════════════════════════════════════════════════════════════
# Tests: /api/history (new)
# ════════════════════════════════════════════════════════════════

async def test_get_history_empty(api):
    """GET /api/history — empty history returns empty list."""
    client, _ = api
    resp = await client.get("/api/history")
    assert resp.status == 200
    data = await resp.json()
    assert "messages" in data
    assert data["messages"] == []


async def test_get_history_with_messages(api):
    """GET /api/history — returns sanitized messages (role/content/timestamp only)."""
    client, components = api
    components.chat_history.add_test_message("user", "你好")
    components.chat_history.add_test_message("assistant", "你好呀")
    resp = await client.get("/api/history")
    assert resp.status == 200
    data = await resp.json()
    assert len(data["messages"]) == 2
    for m in data["messages"]:
        assert set(m.keys()) == {"role", "content", "timestamp"}


async def test_get_history_with_user_id(api):
    """GET /api/history?user_id=xxx — custom user_id accepted."""
    client, components = api
    components.chat_history.add_test_message("user", "test")
    # D 演进：伪造 user_id 会被 _guard_client_identity 拒绝，改为合法查询（persona-scope 解析）
    resp = await client.get("/api/history")
    assert resp.status == 200
    data = await resp.json()
    assert isinstance(data["messages"], list)


async def test_delete_history_last_empty(api):
    """DELETE /api/history/last — succeeds even with no messages."""
    client, _ = api
    resp = await client.delete("/api/history/last")
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    assert data["remaining"] == 0


async def test_delete_history_last_with_messages(api):
    """DELETE /api/history/last — deletes last pair, returns remaining count."""
    client, components = api
    components.chat_history.add_test_message("user", "你好")
    components.chat_history.add_test_message("assistant", "你好呀")
    resp = await client.delete("/api/history/last")
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    assert data["remaining"] == 0


async def test_delete_history_last_partial(api):
    """DELETE /api/history/last — with 4 messages, deletes 2, leaves 2."""
    client, components = api
    components.chat_history.add_test_message("user", "a")
    components.chat_history.add_test_message("assistant", "b")
    components.chat_history.add_test_message("user", "c")
    components.chat_history.add_test_message("assistant", "d")
    resp = await client.delete("/api/history/last")
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    assert data["remaining"] == 2


# ════════════════════════════════════════════════════════════════
# Tests: /api/chat (streaming)
# ════════════════════════════════════════════════════════════════

async def test_chat_streaming(api):
    """POST /api/chat — SSE stream with token + done events."""
    client, _ = api
    resp = await client.post("/api/chat", json={"content": "你好"})
    assert resp.status == 200
    assert "text/event-stream" in resp.headers.get("Content-Type", "")
    body = await resp.text()
    assert "event: token" in body
    assert "event: done" in body
    assert "测试回复" in body


async def test_chat_with_persona_id(api):
    """POST /api/chat with persona_id — regression: passes persona_id to pipeline."""
    client, components = api
    resp = await client.post("/api/chat", json={
        "content": "hello",
        "persona_id": "test_002",
    })
    assert resp.status == 200
    assert len(components.pipeline.calls) == 1
    assert components.pipeline.calls[0]["persona_id"] == "test_002"


async def test_chat_without_persona_id_uses_default(api):
    """POST /api/chat without persona_id — uses DEFAULT_PERSONA_ID."""
    client, components = api
    resp = await client.post("/api/chat", json={"content": "hello"})
    assert resp.status == 200
    assert len(components.pipeline.calls) == 1
    assert components.pipeline.calls[0]["persona_id"] == srv.DEFAULT_PERSONA_ID


async def test_chat_empty_content(api):
    """POST /api/chat — empty content returns 400."""
    client, _ = api
    resp = await client.post("/api/chat", json={"content": ""})
    assert resp.status == 400


async def test_chat_missing_content(api):
    """POST /api/chat — missing content field returns 400."""
    client, _ = api
    resp = await client.post("/api/chat", json={})
    assert resp.status == 400


async def test_chat_invalid_json(api):
    """POST /api/chat — invalid JSON returns 400."""
    client, _ = api
    resp = await client.post(
        "/api/chat",
        data="bad",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status == 400


# ════════════════════════════════════════════════════════════════
# Tests: /api/upload/image
# ════════════════════════════════════════════════════════════════

async def test_upload_image_no_image(api):
    """POST /api/upload/image — no image part returns 400."""
    client, _ = api
    form = aiohttp.FormData()
    form.add_field("caption", "test caption")
    # Force multipart encoding (aiohttp defaults to urlencoded without a file field)
    form.add_field("_dummy", b"x", filename="dummy.txt", content_type="text/plain")
    resp = await client.post("/api/upload/image", data=form)
    assert resp.status == 400


async def test_upload_image_vision_not_configured(api):
    """POST /api/upload/image — image present but vision_manager is None returns 400."""
    client, _ = api
    form = aiohttp.FormData()
    form.add_field(
        "image",
        b"\x89PNG\r\n\x1a\n" + b"\x00" * 100,
        filename="test.png",
        content_type="image/png",
    )
    resp = await client.post("/api/upload/image", data=form)
    assert resp.status == 400
    data = await resp.json()
    assert "error" in data


async def test_upload_image_rejects_non_image(api):
    client, _ = api
    form = aiohttp.FormData()
    form.add_field("image", b"not an image", filename="bad.txt", content_type="text/plain")
    resp = await client.post("/api/upload/image", data=form)
    assert resp.status == 415


async def test_upload_image_uses_conversation_binding(api, tmp_path):
    """图片上传应沿用当前会话的 user_id 与 persona，而不是默认上下文。"""
    client, components = api
    from core.conversation import ConversationStore

    class FakeVision:
        main_is_multimodal = False

        async def process(self, _path, _prompt):
            return "图片描述"

        def build_enhanced_message(self, description, caption):
            return f"{description} {caption}".strip()

    components.vision_manager = FakeVision()
    components.conversation_store = ConversationStore(tmp_path / "conversations.json")
    binding = components.conversation_store.create(
        "web", "", "media-test", "test_002",
    )
    form = aiohttp.FormData()
    form.add_field(
        "image", b"\x89PNG\r\n\x1a\n" + b"\x00" * 100,
        filename="test.png", content_type="image/png",
    )
    form.add_field("conversation_id", binding.conversation_id)

    resp = await client.post("/api/upload/image", data=form)

    assert resp.status == 200
    call = components.pipeline.calls[-1]
    assert call["user_id"] == "web::test_002"
    assert call["persona_id"] == "test_002"


# ════════════════════════════════════════════════════════════════
# Tests: /api/upload/voice
# ════════════════════════════════════════════════════════════════

async def test_upload_voice_no_audio(api):
    """POST /api/upload/voice — no audio part returns 400."""
    client, _ = api
    form = aiohttp.FormData()
    form.add_field("user_id", "test_user")
    # Force multipart encoding (aiohttp defaults to urlencoded without a file field)
    form.add_field("_dummy", b"x", filename="dummy.txt", content_type="text/plain")
    resp = await client.post("/api/upload/voice", data=form)
    assert resp.status == 400


async def test_upload_voice_asr_not_configured(api, monkeypatch):
    """POST /api/upload/voice — audio present but ASR not configured returns 400."""
    client, _ = api
    monkeypatch.setattr(srv, "_try_transcribe", lambda path: None)
    form = aiohttp.FormData()
    form.add_field(
        "audio",
        b"\x00" * 100,
        filename="voice.webm",
        content_type="audio/webm",
    )
    resp = await client.post("/api/upload/voice", data=form)
    assert resp.status == 400
    data = await resp.json()
    assert data.get("need_asr") is True


async def test_upload_voice_rejects_non_audio(api):
    client, _ = api
    form = aiohttp.FormData()
    form.add_field("audio", b"not audio", filename="bad.txt", content_type="text/plain")
    resp = await client.post("/api/upload/voice", data=form)
    assert resp.status == 415


async def test_upload_voice_uses_conversation_binding(api, monkeypatch, tmp_path):
    """语音转写后应在上传时指定的会话中继续对话。"""
    client, components = api
    from core.conversation import ConversationStore

    monkeypatch.setattr(srv, "_try_transcribe", lambda _path: "语音内容")
    components.conversation_store = ConversationStore(tmp_path / "conversations.json")
    binding = components.conversation_store.create(
        "web", "", "voice-test", "test_002",
    )
    form = aiohttp.FormData()
    form.add_field(
        "audio", b"\x00" * 100,
        filename="voice.webm", content_type="audio/webm",
    )
    form.add_field("conversation_id", binding.conversation_id)

    resp = await client.post("/api/upload/voice", data=form)

    assert resp.status == 200
    call = components.pipeline.calls[-1]
    assert call["user_id"] == "web::test_002"
    assert call["persona_id"] == "test_002"


# ════════════════════════════════════════════════════════════════
# Tests: /api/persona (new)
# ════════════════════════════════════════════════════════════════

async def test_list_personas(api):
    """GET /api/persona — returns list of {id, name, avatar}."""
    client, _ = api
    resp = await client.get("/api/persona")
    assert resp.status == 200
    data = await resp.json()
    assert isinstance(data, list)
    assert len(data) == 2
    for p in data:
        assert "id" in p
        assert "name" in p
        assert "avatar" in p


async def test_get_persona(api):
    """GET /api/persona/{id} — returns USER_FIELDS + id."""
    client, _ = api
    resp = await client.get("/api/persona/test_001")
    assert resp.status == 200
    data = await resp.json()
    assert data["id"] == "test_001"
    assert data["name"] == "测试人设"
    assert "age" in data
    assert "gender" in data


async def test_get_persona_not_found(api):
    """GET /api/persona/{id} — unknown id returns 404."""
    client, _ = api
    resp = await client.get("/api/persona/nonexistent")
    assert resp.status == 404


async def test_get_persona_advanced(api):
    """GET /api/persona/{id}/advanced — returns ADVANCED_FIELDS."""
    client, _ = api
    resp = await client.get("/api/persona/test_001/advanced")
    assert resp.status == 200
    data = await resp.json()
    assert "system_prompt" in data
    assert "hard_rules" in data


async def test_get_persona_advanced_not_found(api):
    """GET /api/persona/{id}/advanced — unknown id returns 404."""
    client, _ = api
    resp = await client.get("/api/persona/nonexistent/advanced")
    assert resp.status == 404


async def test_update_persona(api):
    """POST /api/persona/{id} — valid USER_FIELD update."""
    client, components = api
    resp = await client.post("/api/persona/test_001", json={
        "fields": {"name": "新名字"}
    })
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    assert data["persona"]["name"] == "新名字"
    # Verify the fake persona was actually updated
    assert components.persona_loader.get("test_001").name == "新名字"


async def test_update_persona_not_found(api):
    """POST /api/persona/{id} — unknown id returns 404."""
    client, _ = api
    resp = await client.post("/api/persona/nonexistent", json={
        "fields": {"name": "x"}
    })
    assert resp.status == 404


async def test_update_persona_invalid_fields(api):
    """POST /api/persona/{id} — field not in USER_FIELDS ∪ ADVANCED_FIELDS returns 400."""
    client, _ = api
    resp = await client.post("/api/persona/test_001", json={
        "fields": {"invalid_field": "x"}
    })
    assert resp.status == 400


async def test_update_persona_advanced_field(api):
    """POST /api/persona/{id} — advanced field (system_prompt) is accepted."""
    client, components = api
    resp = await client.post("/api/persona/test_001", json={
        "fields": {"system_prompt": "new prompt"}
    })
    assert resp.status == 200
    assert components.persona_loader.get("test_001").system_prompt == "new prompt"


async def test_update_persona_core_text_fields(api):
    client, components = api
    resp = await client.post("/api/persona/test_001", json={
        "fields": {
            "persona_prompt": "独立摄影师",
            "output_examples": "你说：我刚拍到晚霞",
        }
    })
    assert resp.status == 200
    persona = components.persona_loader.get("test_001")
    assert persona.persona_prompt == "独立摄影师"
    assert persona.output_examples == "你说：我刚拍到晚霞"


async def test_update_persona_empty_fields(api):
    """POST /api/persona/{id} — empty fields dict is accepted (no-op)."""
    client, _ = api
    resp = await client.post("/api/persona/test_001", json={"fields": {}})
    assert resp.status == 200


# ════════════════════════════════════════════════════════════════
# Tests: static file serving
# ════════════════════════════════════════════════════════════════

async def test_static_serving(api):
    """GET /static/index.html — static file serving works if dir exists."""
    client, _ = api
    resp = await client.get("/static/index.html")
    # 200 if static dir exists, 404 if not
    assert resp.status in (200, 404)


async def test_static_404_for_missing_file(api):
    """GET /static/nonexistent.file — returns 404."""
    client, _ = api
    resp = await client.get("/static/this_file_does_not_exist_xyz.html")
    assert resp.status == 404


# ════════════════════════════════════════════════════════════════
# Tests: /api/memory (new — T1)
# ════════════════════════════════════════════════════════════════

async def test_get_memory_list_empty(api):
    """GET /api/memory — no memories returns 200 + empty list."""
    client, _ = api
    resp = await client.get("/api/memory")
    assert resp.status == 200
    data = await resp.json()
    assert data == {"messages": [], "total": 0}


async def test_get_memory_list_with_data(api):
    """GET /api/memory — 2 seeded memories returned with 9 fields each."""
    client, components = api
    components.memory_mgr.add_test_memory("m1", "记忆一", level=3)
    components.memory_mgr.add_test_memory("m2", "记忆二", level=2)
    resp = await client.get("/api/memory")
    assert resp.status == 200
    data = await resp.json()
    assert data["total"] == 2
    assert len(data["messages"]) == 2
    expected_fields = {
        "id", "content", "level", "category", "created_at",
        "tags", "source", "confidence", "last_accessed",
    }
    for item in data["messages"]:
        assert set(item.keys()) == expected_fields


async def test_get_memory_list_level_filter(api):
    """GET /api/memory?level_min=3&level_max=5 — filters out level 1."""
    client, components = api
    components.memory_mgr.add_test_memory("m1", "低", level=1)
    components.memory_mgr.add_test_memory("m2", "中", level=3)
    components.memory_mgr.add_test_memory("m3", "高", level=5)
    resp = await client.get("/api/memory?level_min=3&level_max=5")
    assert resp.status == 200
    data = await resp.json()
    assert data["total"] == 2
    levels = {item["level"] for item in data["messages"]}
    assert levels == {3, 5}


async def test_get_memory_list_bad_levels(api):
    """GET /api/memory?level_min=4&level_max=2 — 400 level_min > level_max."""
    client, _ = api
    resp = await client.get("/api/memory?level_min=4&level_max=2")
    assert resp.status == 400
    data = await resp.json()
    assert data == {"error": "level_min must be <= level_max"}


async def test_get_memory_list_bad_offset(api):
    """GET /api/memory?offset=abc — 400 invalid integer."""
    client, _ = api
    resp = await client.get("/api/memory?offset=abc")
    assert resp.status == 400
    data = await resp.json()
    assert "error" in data


async def test_get_memory_detail_found(api):
    """GET /api/memory/{id} — 200 + all 14 Memory fields."""
    client, components = api
    components.memory_mgr.add_test_memory("m1", "详情记忆", level=4)
    resp = await client.get("/api/memory/m1")
    assert resp.status == 200
    data = await resp.json()
    expected_fields = {
        "id", "content", "level", "category", "created_at",
        "last_accessed", "access_count", "tags", "related_memory_ids",
        "superseded_by", "source", "confidence", "forget_score", "archived",
    }
    assert set(data.keys()) == expected_fields
    assert data["id"] == "m1"
    assert data["content"] == "详情记忆"
    assert data["level"] == 4


async def test_get_memory_detail_not_found(api):
    """GET /api/memory/{id} — unknown id returns 404."""
    client, _ = api
    resp = await client.get("/api/memory/nonexistent")
    assert resp.status == 404
    data = await resp.json()
    assert data == {"error": "memory not found"}


# ════════════════════════════════════════════════════════════════
# Tests: /api/life_summary (new — T1)
# ════════════════════════════════════════════════════════════════

async def test_get_life_summary_list(api):
    """GET /api/life_summary — returns summaries with 8 fields each."""
    client, components = api
    components.life_summary._sqlite_storage.add_test_summary("ls1")
    components.life_summary._sqlite_storage.add_test_summary("ls2")
    resp = await client.get("/api/life_summary")
    assert resp.status == 200
    data = await resp.json()
    assert "summaries" in data
    assert data["total"] == 2
    assert len(data["summaries"]) == 2
    expected_fields = {
        "id", "summary_type", "summary", "recent_status",
        "key_events", "message_count", "created_at", "emotional_trends",
    }
    for item in data["summaries"]:
        assert set(item.keys()) == expected_fields


async def test_persona_scope_routes_memory_and_diary_to_role_web_user(api):
    client, components = api
    memory_users = []
    diary_users = []
    original_memories = components.memory_mgr.get_memories
    original_summaries = components.life_summary._sqlite_storage.load_by_user

    def track_memories(user_id, *args, **kwargs):
        memory_users.append(user_id)
        return original_memories(user_id, *args, **kwargs)

    def track_summaries(user_id, *args, **kwargs):
        diary_users.append((user_id, kwargs.get("persona_id", args[1] if len(args) > 1 else "")))
        return original_summaries(user_id, *args, **kwargs)

    components.memory_mgr.get_memories = track_memories
    components.life_summary._sqlite_storage.load_by_user = track_summaries

    memory_response = await client.get("/api/memory?persona_id=test_002")
    diary_response = await client.get("/api/life_summary?persona_id=test_002")

    assert memory_response.status == 200
    assert diary_response.status == 200
    assert memory_users == [build_web_uid("test_002")]
    assert diary_users == [(build_web_uid("test_002"), "test_002")]


async def test_get_life_summary_latest(api):
    """GET /api/life_summary/latest — 200 + single object with 8 fields."""
    client, components = api
    components.life_summary._sqlite_storage.add_test_summary("ls1")
    resp = await client.get("/api/life_summary/latest")
    assert resp.status == 200
    data = await resp.json()
    assert data is not None
    expected_fields = {
        "id", "summary_type", "summary", "recent_status",
        "key_events", "message_count", "created_at", "emotional_trends",
    }
    assert set(data.keys()) == expected_fields


async def test_get_life_summary_latest_empty(api):
    """GET /api/life_summary/latest — no summaries returns 200 + null."""
    client, _ = api
    resp = await client.get("/api/life_summary/latest")
    assert resp.status == 200
    data = await resp.json()
    assert data is None


# ════════════════════════════════════════════════════════════════
# Tests: /api/model/provider POST (new — T1)
# ════════════════════════════════════════════════════════════════

async def test_post_model_provider_add(api):
    """POST /api/model/provider — valid body adds key, returns ok + key."""
    client, _ = api
    body = {
        "key": "newprovider",
        "provider": "openai",
        "model_name": "gpt-4",
        "base_url": "https://api.example.com/v1",
        "api_key": "sk-test",
    }
    resp = await client.post("/api/model/provider", json=body)
    assert resp.status == 200
    data = await resp.json()
    assert data == {"ok": True, "key": "newprovider"}
    # Verify the new key is now in available models
    resp2 = await client.get("/api/model")
    data2 = await resp2.json()
    assert "newprovider" in data2["available"]


async def test_post_model_provider_duplicate_key(api):
    """POST /api/model/provider — existing key returns 400."""
    client, _ = api
    body = {
        "key": "test-model",  # already in fixture settings
        "provider": "openai",
        "model_name": "gpt-4",
        "base_url": "https://api.example.com/v1",
        "api_key": "sk-test",
    }
    resp = await client.post("/api/model/provider", json=body)
    assert resp.status == 400
    data = await resp.json()
    assert data == {"error": "model key already exists"}


async def test_post_model_provider_missing_fields(api):
    """POST /api/model/provider — missing api_key returns 400."""
    client, _ = api
    body = {
        "key": "newprovider",
        "provider": "openai",
        "model_name": "gpt-4",
        "base_url": "https://api.example.com/v1",
        # api_key omitted
    }
    resp = await client.post("/api/model/provider", json=body)
    assert resp.status == 400
    data = await resp.json()
    assert data == {"error": "api_key required"}


async def test_post_model_provider_bad_temperature(api):
    """POST /api/model/provider — non-numeric temperature returns 400."""
    client, _ = api
    body = {
        "key": "newprovider",
        "provider": "openai",
        "model_name": "gpt-4",
        "base_url": "https://api.example.com/v1",
        "api_key": "sk-test",
        "temperature": "hot",
    }
    resp = await client.post("/api/model/provider", json=body)
    assert resp.status == 400
    data = await resp.json()
    assert data == {"error": "temperature must be numeric"}


async def test_post_model_provider_missing_provider(api):
    """POST /api/model/provider — missing provider returns 400."""
    client, _ = api
    body = {
        "key": "newprovider",
        "model_name": "gpt-4",
        "base_url": "https://api.example.com/v1",
        "api_key": "sk-test",
        # provider omitted
    }
    resp = await client.post("/api/model/provider", json=body)
    assert resp.status == 400
    data = await resp.json()
    assert data == {"error": "provider required"}


async def test_post_model_provider_persists_unified_fields(api):
    """POST /api/model/provider — written settings use unified field names
    (provider/model_name/base_url/api_key), NOT legacy (model/api_base).

    Regression guard for the field-name mismatch bug where the POST handler
    wrote `model`/`api_base` but registry._register_from_config read
    `model_name`/`base_url`, causing new providers to fail on restart.
    """
    client, _ = api
    body = {
        "key": "newprovider",
        "provider": "openai",
        "model_name": "gpt-4",
        "base_url": "https://api.example.com/v1",
        "api_key": "sk-test",
        "temperature": 0.7,
        "max_tokens": 1024,
        "presence_penalty": 0.2,
        "frequency_penalty": 0.4,
    }
    resp = await client.post("/api/model/provider", json=body)
    assert resp.status == 200
    # Read back settings.json via GET /api/model + raw file inspection
    settings_path = srv.SETTINGS_PATH
    saved = json.loads(settings_path.read_text(encoding="utf-8-sig"))
    cfg = saved["models"]["newprovider"]
    assert cfg["provider"] == "openai"
    assert cfg["model_name"] == "gpt-4"
    assert cfg["base_url"] == "https://api.example.com/v1"
    assert cfg["api_key"] == ""
    assert cfg["api_key_ref"] == "model/newprovider"
    assert srv.resolve_config_secret(cfg, manager=srv._secret_manager()) == "sk-test"
    assert cfg["temperature"] == 0.7
    assert cfg["max_tokens"] == 1024
    assert cfg["presence_penalty"] == 0.2
    assert cfg["frequency_penalty"] == 0.4
    # Legacy names MUST NOT be present
    assert "model" not in cfg
    assert "api_base" not in cfg


# ════════════════════════════════════════════════════════════════
# Tests: /api/model/{model_key} DELETE (new — T1)
# ════════════════════════════════════════════════════════════════

async def test_delete_model_provider(api):
    """DELETE /api/model/{key} — existing key (after adding 2nd) returns ok."""
    client, _ = api
    # Fixture has 1 model (test-model); add a second one first
    add_body = {
        "key": "second-model",
        "provider": "openai",
        "model_name": "gpt-4",
        "base_url": "https://api.example.com/v1",
        "api_key": "sk-test",
    }
    add_resp = await client.post("/api/model/provider", json=add_body)
    assert add_resp.status == 200
    # Now delete the second model
    resp = await client.delete("/api/model/second-model")
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    # Verify second-model is no longer in available
    resp2 = await client.get("/api/model")
    data2 = await resp2.json()
    assert "second-model" not in data2["available"]


async def test_delete_model_provider_not_found(api):
    """DELETE /api/model/{key} — unknown key returns 404."""
    client, _ = api
    resp = await client.delete("/api/model/nonexistent")
    assert resp.status == 404
    data = await resp.json()
    assert data == {"error": "model key not found"}


async def test_delete_last_model_prevention(api):
    """DELETE /api/model/{key} — deleting the only model returns 400."""
    client, _ = api
    # Fixture has only test-model; deleting it should be prevented
    resp = await client.delete("/api/model/test-model")
    assert resp.status == 400
    data = await resp.json()
    assert data == {"error": "cannot delete last model"}


async def test_delete_default_model_auto_reassign(api):
    """DELETE /api/model/{default} — deleting default reassigns to remaining."""
    client, _ = api
    # Fixture has test-model as default; add a second model first
    add_body = {
        "key": "second-model",
        "provider": "openai",
        "model_name": "gpt-4",
        "base_url": "https://api.example.com/v1",
        "api_key": "sk-test",
    }
    add_resp = await client.post("/api/model/provider", json=add_body)
    assert add_resp.status == 200
    # Delete the default (test-model) — should reassign to second-model
    resp = await client.delete("/api/model/test-model")
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    assert data["current"] == "second-model"


# ════════════════════════════════════════════════════════════════
# Tests: registry backward compat — old field names still load (T1)
# ════════════════════════════════════════════════════════════════

def test_registry_loads_new_field_names(tmp_path, monkeypatch):
    """registry._register_from_config — new field names (provider/model_name/
    base_url) load correctly and register the model.

    End-to-end: POST /api/model/provider writes unified fields, then on restart
    registry reads them back without env var (api_key fallback from cfg).
    """
    from core.llm.registry import LLMRegistry

    # No env var set → registry must fall back to cfg["api_key"]
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("NEWPROVIDER_API_KEY", raising=False)

    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({
        "default_model": "newprovider",
        "models": {
            "newprovider": {
                "provider": "openai",
                "model_name": "gpt-4",
                "base_url": "https://api.example.com/v1",
                "api_key": "sk-test",
                "temperature": 0.7,
                "max_tokens": 1024,
                "presence_penalty": 0.2,
                "frequency_penalty": 0.4,
            },
        },
        "advanced": {"max_retries": 2},
    }, ensure_ascii=False), encoding="utf-8")

    registry = LLMRegistry(str(settings_file))
    assert "newprovider" in registry.available_models
    llm = registry.get("newprovider")
    assert llm.model_name == "gpt-4"
    assert llm.api_key == "sk-test"
    assert llm.base_url == "https://api.example.com/v1"
    assert llm.temperature == 0.7
    assert llm.max_tokens == 1024
    assert llm.presence_penalty == 0.2
    assert llm.frequency_penalty == 0.4


def test_registry_loads_legacy_field_names(tmp_path, monkeypatch):
    """registry._register_from_config — legacy field names (model/api_base)
    still load via backward compat.

    Guards existing settings.json files written by the old POST handler
    from failing on restart after the field-name unification.
    """
    from core.llm.registry import LLMRegistry

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LEGACY_API_KEY", raising=False)

    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({
        "default_model": "legacy",
        "models": {
            "legacy": {
                # Old field names — no provider, model instead of model_name,
                # api_base instead of base_url
                "model": "gpt-3.5-turbo",
                "api_base": "https://api.legacy.example.com/v1",
                "api_key": "sk-legacy",
            },
        },
        "advanced": {"max_retries": 2},
    }, ensure_ascii=False), encoding="utf-8")

    registry = LLMRegistry(str(settings_file))
    assert "legacy" in registry.available_models
    llm = registry.get("legacy")
    # Backward compat: model_name read from "model", base_url from "api_base"
    assert llm.model_name == "gpt-3.5-turbo"
    assert llm.api_key == "sk-legacy"
    assert llm.base_url == "https://api.legacy.example.com/v1"
    # provider defaults to "openai" when absent
    # (verified indirectly: OpenAICompatibleLLM was instantiated)


def test_registry_env_api_key_takes_precedence(tmp_path, monkeypatch):
    """registry._register_from_config — env var api_key wins over cfg api_key."""
    from core.llm.registry import LLMRegistry

    # env var name is derived from model key: ENVTEST_API_KEY
    monkeypatch.setenv("ENVTEST_API_KEY", "sk-from-env")

    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({
        "default_model": "envtest",
        "models": {
            "envtest": {
                "provider": "openai",
                "model_name": "gpt-4",
                "base_url": "https://api.example.com/v1",
                "api_key": "sk-from-cfg",
            },
        },
    }, ensure_ascii=False), encoding="utf-8")

    registry = LLMRegistry(str(settings_file))
    llm = registry.get("envtest")
    assert llm.api_key == "sk-from-env"


def test_registry_skips_model_without_api_key(tmp_path, monkeypatch):
    """registry._register_from_config — no env var AND no cfg api_key → skip."""
    from core.llm.registry import LLMRegistry

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("NOKEY_API_KEY", raising=False)

    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({
        "default_model": "nokey",
        "models": {
            "nokey": {
                "provider": "openai",
                "model_name": "gpt-4",
                "base_url": "https://api.example.com/v1",
                # no api_key, no env var
            },
        },
    }, ensure_ascii=False), encoding="utf-8")

    registry = LLMRegistry(str(settings_file))
    assert "nokey" not in registry.available_models


async def test_post_provider_then_registry_loads(tmp_path, monkeypatch):
    """End-to-end: POST /api/model/provider writes unified fields, then a fresh
    LLMRegistry loads settings.json and the new provider registers successfully.

    This is the core regression test for the original bug: POST wrote
    model/api_base but registry read model_name/base_url → new providers
    failed registration on restart.
    """
    # No env vars → forces registry to use cfg api_key fallback
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("E2E_API_KEY", raising=False)

    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({
        "default_model": "test-model",
        "models": {"test-model": {"temperature": 1.0, "max_tokens": 4096}},
        "advanced": {"segment_max_length": 16},
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(srv, "SETTINGS_PATH", settings_file)
    monkeypatch.setattr(srv, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(srv, "load_advanced", lambda: {
        "segment_max_length": 16, "debounce_seconds": 3,
        "summarize_threshold": 15, "max_retries": 2,
        "proactive_enabled": True, "auto_extract_memory": False,
    })

    components = FakeAppComponents()
    app = srv._make_app(components)
    server = TestServer(app)
    cli = TestClient(server)
    await cli.start_server()
    try:
        body = {
            "key": "e2e-provider",
            "provider": "openai",
            "model_name": "gpt-4",
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-e2e",
            "temperature": 0.5,
            "max_tokens": 512,
        }
        resp = await cli.post("/api/model/provider", json=body)
        assert resp.status == 200
        assert (await resp.json()) == {"ok": True, "key": "e2e-provider"}
    finally:
        await cli.close()

    # Now simulate restart: a fresh registry loads the updated settings.json
    from core.llm.registry import LLMRegistry
    registry = LLMRegistry(str(settings_file))
    assert "e2e-provider" in registry.available_models
    llm = registry.get("e2e-provider")
    assert llm.model_name == "gpt-4"
    assert llm.api_key == "sk-e2e"
    assert llm.base_url == "https://api.example.com/v1"
    assert llm.temperature == 0.5
    assert llm.max_tokens == 512


# ════════════════════════════════════════════════════════════════
# Tests: /api/persona/{id}/avatar (new — T2)
# ════════════════════════════════════════════════════════════════

# Minimal valid 1x1 PNG (no external file needed — privacy-safe placeholder).
_PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


async def test_upload_avatar_success(api):
    """POST /api/persona/{id}/avatar — png upload round-trip: file saved, GET list reflects URL, GET /avatars/X serves image, DELETE clears."""
    client, components = api
    form = aiohttp.FormData()
    form.add_field(
        "file", _PNG_1X1, filename="avatar.png", content_type="image/png",
    )
    resp = await client.post("/api/persona/test_001/avatar", data=form)
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    assert data["avatar_url"] == "/avatars/test_001.png"

    # personas.json-side: avatar field updated via loader.update
    assert components.persona_loader.get("test_001").avatar == "/avatars/test_001.png"

    # GET /api/persona reflects the actual avatar URL (not None)
    resp = await client.get("/api/persona")
    assert resp.status == 200
    personas = await resp.json()
    target = next(p for p in personas if p["id"] == "test_001")
    assert target["avatar"] == "/avatars/test_001.png"

    # GET /avatars/test_001.png serves the image bytes
    resp = await client.get("/avatars/test_001.png")
    assert resp.status == 200
    assert resp.headers.get("Content-Type", "").startswith("image/")
    body = await resp.read()
    assert body == _PNG_1X1

    # DELETE clears file + field
    resp = await client.delete("/api/persona/test_001/avatar")
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    assert components.persona_loader.get("test_001").avatar == ""

    # File gone → static route 404
    resp = await client.get("/avatars/test_001.png")
    assert resp.status == 404

    # GET /api/persona now shows empty avatar
    resp = await client.get("/api/persona")
    personas = await resp.json()
    target = next(p for p in personas if p["id"] == "test_001")
    assert target["avatar"] == ""


async def test_upload_avatar_too_large(api):
    """POST /api/persona/{id}/avatar — file >2MB returns 413."""
    client, _ = api
    oversized = b"\x00" * (2 * 1024 * 1024 + 1)
    form = aiohttp.FormData()
    form.add_field(
        "file", oversized, filename="big.png", content_type="image/png",
    )
    resp = await client.post("/api/persona/test_001/avatar", data=form)
    assert resp.status == 413
    data = await resp.json()
    assert "too large" in data["error"]


async def test_upload_avatar_wrong_type(api):
    """POST /api/persona/{id}/avatar — non-image content type returns 415."""
    client, _ = api
    form = aiohttp.FormData()
    form.add_field(
        "file", b"not an image", filename="note.txt", content_type="text/plain",
    )
    resp = await client.post("/api/persona/test_001/avatar", data=form)
    assert resp.status == 415
    data = await resp.json()
    assert "unsupported content type" in data["error"]


async def test_upload_avatar_nonexistent_persona(api):
    """POST /api/persona/{id}/avatar — unknown persona returns 404."""
    client, _ = api
    form = aiohttp.FormData()
    form.add_field(
        "file", _PNG_1X1, filename="avatar.png", content_type="image/png",
    )
    resp = await client.post("/api/persona/nonexistent/avatar", data=form)
    assert resp.status == 404
    data = await resp.json()
    assert data["error"] == "persona not found"


async def test_delete_avatar_nonexistent_persona(api):
    """DELETE /api/persona/{id}/avatar — unknown persona returns 404 (orphan cleanup still runs)."""
    client, _ = api
    resp = await client.delete("/api/persona/nonexistent/avatar")
    assert resp.status == 404
    data = await resp.json()
    assert data["error"] == "persona not found"
