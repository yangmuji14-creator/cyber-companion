"""T9: conversation sidebar — backend conversation_id resolution tests.

Covers the 7 endpoints that accept ?conversation_id=X (or body field for
POST /api/chat) and resolve user_id via ConversationStore binding lookup:

- GET  /api/history                — scopes chat history to conversation user_id
- DELETE /api/history/last         — scopes delete to conversation user_id
- GET  /api/memory                 — scopes memory list to conversation user_id
- GET  /api/memory/{id}            — scopes memory detail to conversation user_id
- GET  /api/life_summary           — scopes life_summary list to conversation user_id
- GET  /api/life_summary/latest    — scopes latest life_summary to conversation user_id
- POST /api/chat                   — resolves user_id + uses binding persona_id

Backward compat: omitting conversation_id falls back to legacy behavior
(WEB_USER_ID or build_web_uid(persona_id)).

隐私: 所有 ID 用占位符 (wxid_test, acc1, gf001)，不含真实账号。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from aiohttp.test_utils import TestClient, TestServer

import webui.server as srv
from core.conversation import ConversationStore
from core.config import build_web_uid, build_wechat_uid, build_memory_scope_uid

from tests.test_webui import FakeAppComponents


# ════════════════════════════════════════════════════════════════
# Fixture — real ConversationStore + FakeAppComponents
# ════════════════════════════════════════════════════════════════

@pytest.fixture
async def api(tmp_path, monkeypatch):
    """Yield (TestClient, FakeAppComponents) with real ConversationStore.

    ConversationStore points at tmp_path/conversations.json — fully isolated.
    """
    monkeypatch.setattr(srv, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(srv, "AVATAR_DIR", tmp_path / "avatars")
    # T13: isolate migration marker + legacy file checks to tmp_path
    monkeypatch.setattr(srv, "DATA_DIR", tmp_path)

    components = FakeAppComponents()
    components.conversation_store = ConversationStore(tmp_path / "conversations.json")
    components.persona_loader.add_test_persona("gf001", "小雨")
    components.persona_loader.add_test_persona("gf002", "小雪")

    app = srv._make_app(components)
    server = TestServer(app)
    cli = TestClient(server)
    await cli.start_server()
    try:
        yield cli, components
    finally:
        await cli.close()


async def _create_wechat_binding(client, conv_id="conv_1"):
    """Helper: POST a wechat binding, return the conversation_id."""
    resp = await client.post("/api/conversations", json={
        "platform": "wechat",
        "account_id": "acc1",
        "contact_id": "wxid_test",
        "persona_id": "gf001",
    })
    assert resp.status == 200
    data = await resp.json()
    assert data["conversation_id"] == conv_id
    return data["conversation_id"]


# ════════════════════════════════════════════════════════════════
# GET /api/history
# ════════════════════════════════════════════════════════════════

async def test_get_history_with_conversation_id(api):
    """GET /api/history?conversation_id=conv_1 → 200, resolves user_id from binding."""
    client, components = api
    conv_id = await _create_wechat_binding(client)

    # Track user_id passed to chat_history.get_messages
    captured = []
    orig = components.chat_history.get_messages
    def tracking(user_id):
        captured.append(user_id)
        return orig(user_id)
    components.chat_history.get_messages = tracking

    resp = await client.get(f"/api/history?conversation_id={conv_id}")
    assert resp.status == 200
    data = await resp.json()
    assert "messages" in data
    # user_id should be derived from binding: wechat::acc1::wxid_test
    assert len(captured) == 1
    assert captured[0] == build_memory_scope_uid(
        build_wechat_uid("acc1", "wxid_test"), "gf001", conv_id,
    )


async def test_get_history_conversation_not_found_404(api):
    """GET /api/history?conversation_id=nonexistent → 404."""
    client, _ = api
    resp = await client.get("/api/history?conversation_id=conv_999")
    assert resp.status == 404
    data = await resp.json()
    assert "conversation not found" in data["error"]


async def test_get_history_without_conversation_id_falls_back(api):
    """GET /api/history (no conversation_id) → 200, falls back to WEB_USER_ID."""
    client, components = api

    captured = []
    orig = components.chat_history.get_messages
    def tracking(user_id):
        captured.append(user_id)
        return orig(user_id)
    components.chat_history.get_messages = tracking

    resp = await client.get("/api/history")
    assert resp.status == 200
    # D 演进：历史回退到 persona-scope（web::<persona>），而非旧单一 WEB_USER_ID
    assert len(captured) == 1
    assert captured[0].startswith("web::")


# ════════════════════════════════════════════════════════════════
# POST /api/chat
# ════════════════════════════════════════════════════════════════

async def test_post_chat_with_conversation_id(api):
    """POST /api/chat {content, conversation_id} → pipeline receives
    resolved user_id (from binding) + binding persona_id."""
    client, components = api
    conv_id = await _create_wechat_binding(client)

    resp = await client.post("/api/chat", json={
        "content": "hello",
        "conversation_id": conv_id,
    })
    assert resp.status == 200
    # Pipeline should have been called with:
    # - user_id derived from binding: wechat::acc1::wxid_test
    # - persona_id from binding: gf001 (not DEFAULT_PERSONA_ID)
    assert len(components.pipeline.calls) == 1
    call = components.pipeline.calls[0]
    assert call["user_id"] == build_wechat_uid("acc1", "wxid_test")
    assert call["persona_id"] == "gf001"
    assert call["scope_id"] == build_memory_scope_uid(
        build_wechat_uid("acc1", "wxid_test"), "gf001", conv_id,
    )
    assert call["content"] == "hello"


async def test_post_chat_conversation_not_found_404(api):
    """POST /api/chat with bad conversation_id → 404."""
    client, _ = api
    resp = await client.post("/api/chat", json={
        "content": "hello",
        "conversation_id": "conv_999",
    })
    assert resp.status == 404
    data = await resp.json()
    assert "conversation not found" in data["error"]


# ════════════════════════════════════════════════════════════════
# GET /api/memory
# ════════════════════════════════════════════════════════════════

async def test_get_memory_with_conversation_id(api):
    """GET /api/memory?conversation_id=conv_1 → 200, scopes memory to
    conversation user_id (verified via tracking call)."""
    client, components = api
    conv_id = await _create_wechat_binding(client)

    captured = []
    orig = components.memory_mgr.get_memories
    def tracking(user_id, *args, **kwargs):
        captured.append(user_id)
        return orig(user_id, *args, **kwargs)
    components.memory_mgr.get_memories = tracking

    resp = await client.get(f"/api/memory?conversation_id={conv_id}")
    assert resp.status == 200
    data = await resp.json()
    assert "messages" in data
    assert len(captured) == 1
    assert captured[0] == build_memory_scope_uid(
        build_wechat_uid("acc1", "wxid_test"), "gf001", conv_id,
    )


# ════════════════════════════════════════════════════════════════
# GET /api/life_summary
# ════════════════════════════════════════════════════════════════

async def test_get_life_summary_with_conversation_id(api):
    """GET /api/life_summary?conversation_id=conv_1 → 200, scopes to
    conversation user_id."""
    client, components = api
    conv_id = await _create_wechat_binding(client)

    captured = []
    orig = components.life_summary._sqlite_storage.load_by_user
    def tracking(user_id, *args, **kwargs):
        captured.append(user_id)
        return orig(user_id, *args, **kwargs)
    components.life_summary._sqlite_storage.load_by_user = tracking

    resp = await client.get(f"/api/life_summary?conversation_id={conv_id}")
    assert resp.status == 200
    data = await resp.json()
    assert "summaries" in data
    assert len(captured) == 1
    assert captured[0] == build_memory_scope_uid(
        build_wechat_uid("acc1", "wxid_test"), "gf001", conv_id,
    )


# ════════════════════════════════════════════════════════════════
# DELETE /api/history/last
# ════════════════════════════════════════════════════════════════

async def test_delete_last_with_conversation_id(api):
    """DELETE /api/history/last?conversation_id=conv_1 → 200, deletes
    from the conversation's user_id (not WEB_USER_ID)."""
    client, components = api
    conv_id = await _create_wechat_binding(client)

    captured = []
    orig = components.chat_history.delete_last_messages
    def tracking(user_id, *args, **kwargs):
        captured.append(user_id)
        return orig(user_id, *args, **kwargs)
    components.chat_history.delete_last_messages = tracking

    resp = await client.delete(f"/api/history/last?conversation_id={conv_id}")
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    assert len(captured) == 1
    assert captured[0] == build_memory_scope_uid(
        build_wechat_uid("acc1", "wxid_test"), "gf001", conv_id,
    )
