"""WeChat account management + SSE QR login route tests — T8.

Covers:
- GET  /api/wechat/accounts              — list accounts + status
- POST /api/wechat/accounts              — create account (200/400/409)
- DELETE /api/wechat/accounts/{id}       — delete account (200/404)
- GET  /api/wechat/login/{id}/qrcode     — SSE QR login (success/failure/409)
- POST /api/wechat/logout/{id}           — logout (200/404)
- GET  /api/wechat/status/{id}           — status (200/404)

The weixin_ilink SDK is ALWAYS mocked via sys.modules — no real WeChat login
is ever triggered. The fake login() calls on_qrcode + on_status_change
synchronously, then writes fake creds to save_to and returns them.

隐私: All IDs use placeholders (testacc, testacc2, fake_wxid). No real accounts.
"""

import asyncio
import json
import sys
import threading
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from aiohttp.test_utils import TestClient, TestServer

import webui.server as srv
from core.conversation import ConversationStore
from tests.test_webui import FakeAppComponents


# ════════════════════════════════════════════════════════════════
# Fake weixin_ilink SDK — module-level factory
# ════════════════════════════════════════════════════════════════

_FAKE_CREDS = {"wxid": "fake_wxid", "nickname": "fake_user", "token": "fake_token"}


def _make_fake_weixin_ilink(*, fail=False, block_event=None):
    """Build a fake weixin_ilink module for sys.modules injection.

    Args:
        fail: if True, login() raises RuntimeError.
        block_event: if provided, login() blocks on event.wait() before
            returning — used to test concurrent-login 409.
    """
    fake_module = types.ModuleType("weixin_ilink")

    def fake_login(save_to, on_qrcode=None, on_status_change=None):
        if fail:
            raise RuntimeError("fake login failure")
        if on_qrcode is not None:
            on_qrcode("http://fake-qr-url")
        if on_status_change is not None:
            on_status_change("scaned")
            on_status_change("confirmed")
        if block_event is not None:
            block_event.wait(timeout=10)
        # Write fake creds to save_to (mirrors real SDK behavior)
        with open(save_to, "w", encoding="utf-8") as f:
            json.dump(_FAKE_CREDS, f)
        return _FAKE_CREDS

    fake_module.login = fake_login
    return fake_module


# ════════════════════════════════════════════════════════════════
# Fixture — patched settings + creds dir + faked components
# ════════════════════════════════════════════════════════════════

@pytest.fixture
async def api(monkeypatch, tmp_path):
    """Yield (TestClient, FakeAppComponents) with isolated settings + creds dir.

    settings.json starts with NO wechat accounts configured. Each test adds
    accounts via POST /api/wechat/accounts as needed.
    """
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(json.dumps({
        "default_model": "test-model",
        "models": {"test-model": {"temperature": 1.0, "max_tokens": 4096}},
        "advanced": {
            "segment_max_length": 16,
            "adapters": {"wechat": {"accounts": []}},
        },
    }, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(srv, "SETTINGS_PATH", settings_file)
    monkeypatch.setattr(srv, "WECHAT_CREDS_DIR", tmp_path / "credentials")
    monkeypatch.setattr(srv, "load_advanced", lambda: {
        "segment_max_length": 16, "debounce_seconds": 3,
        "summarize_threshold": 15, "max_retries": 2,
        "proactive_enabled": True, "auto_extract_memory": False,
        "adapters": {"wechat": {"accounts": []}},
    })
    monkeypatch.setattr(srv, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(srv, "AVATAR_DIR", tmp_path / "avatars")

    # Clear login locks from previous tests
    srv._wechat_login_locks.clear()

    components = FakeAppComponents()
    components.adapter_manager = None  # no AdapterManager injected in tests

    app = srv._make_app(components)
    server = TestServer(app)
    cli = TestClient(server)
    await cli.start_server()
    try:
        yield cli, components
    finally:
        await cli.close()


def _parse_sse_events(body: str) -> list[tuple[str, dict]]:
    """Parse SSE body into a list of (event_name, data_dict) tuples."""
    events = []
    current_event = None
    current_data_lines = []
    for line in body.split("\n"):
        if line.startswith("event: "):
            current_event = line[len("event: "):].strip()
        elif line.startswith("data: "):
            current_data_lines.append(line[len("data: "):])
        elif line == "" and current_event is not None:
            data_str = "\n".join(current_data_lines)
            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                data = {"raw": data_str}
            events.append((current_event, data))
            current_event = None
            current_data_lines = []
    return events


# ════════════════════════════════════════════════════════════════
# Tests: GET /api/wechat/accounts
# ════════════════════════════════════════════════════════════════

async def test_list_accounts_empty(api):
    """GET /api/wechat/accounts — no accounts configured returns empty list."""
    client, _ = api
    resp = await client.get("/api/wechat/accounts")
    assert resp.status == 200
    data = await resp.json()
    assert data == []


async def test_list_accounts_with_config(api):
    """GET /api/wechat/accounts — two accounts returned with has_credentials status."""
    client, _ = api
    # Create two accounts
    await client.post("/api/wechat/accounts", json={"id": "acc1", "enabled": True})
    await client.post("/api/wechat/accounts", json={"id": "acc2", "enabled": False})
    # Create credentials file for acc1 only
    srv.WECHAT_CREDS_DIR.mkdir(parents=True, exist_ok=True)
    (srv.WECHAT_CREDS_DIR / "wechat_acc1.json").write_text("{}", encoding="utf-8")

    resp = await client.get("/api/wechat/accounts")
    assert resp.status == 200
    data = await resp.json()
    assert len(data) == 2
    ids = {a["id"] for a in data}
    assert ids == {"acc1", "acc2"}
    acc1 = next(a for a in data if a["id"] == "acc1")
    acc2 = next(a for a in data if a["id"] == "acc2")
    assert acc1["has_credentials"] is True
    assert acc2["has_credentials"] is False
    assert acc1["enabled"] is True
    assert acc2["enabled"] is False
    assert acc1["adapter_running"] is False  # adapter_manager is None
    # Each account has all required fields
    for a in data:
        assert {"id", "enabled", "auto_start", "has_credentials", "adapter_running"} <= set(a.keys())


# ════════════════════════════════════════════════════════════════
# Tests: POST /api/wechat/accounts
# ════════════════════════════════════════════════════════════════

async def test_create_account_200(api):
    """POST /api/wechat/accounts — valid id returns 200, settings updated."""
    client, _ = api
    resp = await client.post("/api/wechat/accounts", json={
        "id": "acc2", "enabled": True, "auto_start": False,
    })
    assert resp.status == 200
    data = await resp.json()
    assert data["id"] == "acc2"
    assert data["enabled"] is True
    assert data["auto_start"] is False
    # GET list includes acc2
    resp2 = await client.get("/api/wechat/accounts")
    data2 = await resp2.json()
    assert any(a["id"] == "acc2" for a in data2)
    # settings.json persisted with new array format
    saved = json.loads(srv.SETTINGS_PATH.read_text(encoding="utf-8-sig"))
    accounts = saved["advanced"]["adapters"]["wechat"]["accounts"]
    assert any(a["id"] == "acc2" for a in accounts)


async def test_account_role_can_be_selected_and_updated(api, tmp_path):
    client, components = api
    components.persona_loader.add_test_persona("role_a", "角色 A")
    components.persona_loader.add_test_persona("role_b", "角色 B")
    components.conversation_store = ConversationStore(tmp_path / "conversations.json")

    created = await client.post("/api/wechat/accounts", json={
        "id": "roleacc", "persona_id": "role_a",
    })
    assert created.status == 200
    assert (await created.json())["persona_id"] == "role_a"

    binding = components.conversation_store.create(
        "wechat", "roleacc", "internal-contact", "role_a"
    )
    changed = await client.patch("/api/wechat/accounts/roleacc", json={
        "persona_id": "role_b",
    })
    assert changed.status == 200
    payload = await changed.json()
    assert payload["persona_name"] == "角色 B"
    assert payload["bindings_updated"] == 1
    assert components.conversation_store.get(binding.conversation_id).persona_id == "role_b"

    listed = await client.get("/api/wechat/accounts")
    account = next(item for item in await listed.json() if item["id"] == "roleacc")
    assert account["persona_id"] == "role_b"
    assert account["persona_name"] == "角色 B"


async def test_create_account_default_id_200(api):
    """POST /api/wechat/accounts — id='default' is valid (exempt from length rule)."""
    client, _ = api
    resp = await client.post("/api/wechat/accounts", json={"id": "default"})
    assert resp.status == 200
    data = await resp.json()
    assert data["id"] == "default"


async def test_create_account_duplicate_409(api):
    """POST /api/wechat/accounts — duplicate id returns 409."""
    client, _ = api
    await client.post("/api/wechat/accounts", json={"id": "acc1"})
    resp = await client.post("/api/wechat/accounts", json={"id": "acc1"})
    assert resp.status == 409
    data = await resp.json()
    assert "already exists" in data["error"]


async def test_create_account_invalid_id_400(api):
    """POST /api/wechat/accounts — invalid ids (path traversal, too short, special chars) return 400."""
    client, _ = api
    invalid_ids = ["../etc", "ab", "a!b", "a b", "", "a" * 33, "a/b", "a\\b"]
    for bad_id in invalid_ids:
        resp = await client.post("/api/wechat/accounts", json={"id": bad_id})
        assert resp.status == 400, f"id={bad_id!r} should return 400, got {resp.status}"


async def test_create_account_invalid_json_400(api):
    """POST /api/wechat/accounts — invalid JSON returns 400."""
    client, _ = api
    resp = await client.post(
        "/api/wechat/accounts",
        data="not json",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status == 400


# ════════════════════════════════════════════════════════════════
# Tests: DELETE /api/wechat/accounts/{account_id}
# ════════════════════════════════════════════════════════════════

async def test_delete_account_200(api):
    """DELETE /api/wechat/accounts/{id} — removes from settings + deletes creds file."""
    client, _ = api
    await client.post("/api/wechat/accounts", json={"id": "acc1"})
    # Create creds file
    srv.WECHAT_CREDS_DIR.mkdir(parents=True, exist_ok=True)
    creds_file = srv.WECHAT_CREDS_DIR / "wechat_acc1.json"
    creds_file.write_text("{}", encoding="utf-8")
    assert creds_file.exists()

    resp = await client.delete("/api/wechat/accounts/acc1")
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    # Creds file deleted
    assert not creds_file.exists()
    # Account removed from settings
    resp2 = await client.get("/api/wechat/accounts")
    data2 = await resp2.json()
    assert not any(a["id"] == "acc1" for a in data2)


async def test_delete_account_404(api):
    """DELETE /api/wechat/accounts/{id} — unknown id returns 404."""
    client, _ = api
    resp = await client.delete("/api/wechat/accounts/nonexistent")
    assert resp.status == 404


async def test_delete_account_default_removes_wechat_json(api):
    """DELETE /api/wechat/accounts/default — deletes wechat.json (not wechat_default.json)."""
    client, _ = api
    await client.post("/api/wechat/accounts", json={"id": "default"})
    srv.WECHAT_CREDS_DIR.mkdir(parents=True, exist_ok=True)
    creds_file = srv.WECHAT_CREDS_DIR / "wechat.json"
    creds_file.write_text("{}", encoding="utf-8")
    resp = await client.delete("/api/wechat/accounts/default")
    assert resp.status == 200
    assert not creds_file.exists()


# ════════════════════════════════════════════════════════════════
# Tests: GET /api/wechat/login/{account_id}/qrcode (SSE)
# ════════════════════════════════════════════════════════════════

async def test_sse_login_success(api, monkeypatch):
    """GET /api/wechat/login/{id}/qrcode — mocked SDK streams qrcode + status + done events, creates creds file."""
    client, _ = api
    await client.post("/api/wechat/accounts", json={"id": "testacc"})

    # Inject fake weixin_ilink module
    fake_module = _make_fake_weixin_ilink()
    monkeypatch.setitem(sys.modules, "weixin_ilink", fake_module)

    resp = await client.get("/api/wechat/login/testacc/qrcode")
    assert resp.status == 200
    assert "text/event-stream" in resp.headers.get("Content-Type", "")
    body = await resp.text()

    events = _parse_sse_events(body)
    event_names = [e[0] for e in events]
    assert "qrcode" in event_names
    assert "status" in event_names
    assert "done" in event_names

    # qrcode event has qr_url
    qr_event = next(e[1] for e in events if e[0] == "qrcode")
    assert qr_event["qr_url"] == "http://fake-qr-url"

    # done event has ok: true
    done_event = next(e[1] for e in events if e[0] == "done")
    assert done_event["ok"] is True

    # Credentials file created
    creds_path = srv.WECHAT_CREDS_DIR / "wechat_testacc.json"
    assert creds_path.exists()
    saved_creds = json.loads(creds_path.read_text(encoding="utf-8"))
    assert saved_creds["wxid"] == "fake_wxid"


async def test_sse_login_failure(api, monkeypatch):
    """GET /api/wechat/login/{id}/qrcode — SDK raises → done event with ok:false."""
    client, _ = api
    await client.post("/api/wechat/accounts", json={"id": "testacc"})

    fake_module = _make_fake_weixin_ilink(fail=True)
    monkeypatch.setitem(sys.modules, "weixin_ilink", fake_module)

    resp = await client.get("/api/wechat/login/testacc/qrcode")
    assert resp.status == 200
    body = await resp.text()
    events = _parse_sse_events(body)
    done_event = next(e[1] for e in events if e[0] == "done")
    assert done_event["ok"] is False
    assert "error" in done_event
    assert "fake login failure" in done_event["error"]


async def test_sse_login_account_not_configured_404(api, monkeypatch):
    """GET /api/wechat/login/{id}/qrcode — account not in config returns 404 (not SSE)."""
    client, _ = api
    resp = await client.get("/api/wechat/login/nonexistent/qrcode")
    assert resp.status == 404


async def test_sse_login_duplicate_409(api, monkeypatch):
    """GET /api/wechat/login/{id}/qrcode — concurrent login to same account returns 409.

    Pre-acquires the per-account lock so the handler sees it as locked.
    """
    client, _ = api
    await client.post("/api/wechat/accounts", json={"id": "testacc"})

    # Pre-acquire the lock to simulate in-progress login
    lock = asyncio.Lock()
    await lock.acquire()
    srv._wechat_login_locks["testacc"] = lock
    try:
        resp = await client.get("/api/wechat/login/testacc/qrcode")
        assert resp.status == 409
        data = await resp.json()
        assert "already in progress" in data["error"]
    finally:
        lock.release()
        srv._wechat_login_locks.pop("testacc", None)


async def test_sse_login_status_mapping(api, monkeypatch):
    """GET /api/wechat/login/{id}/qrcode — SDK status 'scaned' maps to 'scanning', 'confirmed' to 'confirmed'."""
    client, _ = api
    await client.post("/api/wechat/accounts", json={"id": "testacc"})

    fake_module = _make_fake_weixin_ilink()
    monkeypatch.setitem(sys.modules, "weixin_ilink", fake_module)

    resp = await client.get("/api/wechat/login/testacc/qrcode")
    assert resp.status == 200
    body = await resp.text()
    events = _parse_sse_events(body)
    status_events = [e[1] for e in events if e[0] == "status"]
    statuses = [s["status"] for s in status_events]
    assert "scanning" in statuses
    assert "confirmed" in statuses


# ════════════════════════════════════════════════════════════════
# Tests: POST /api/wechat/logout/{account_id}
# ════════════════════════════════════════════════════════════════

async def test_logout_200(api):
    """POST /api/wechat/logout/{id} — deletes creds file, returns 200."""
    client, _ = api
    await client.post("/api/wechat/accounts", json={"id": "testacc"})
    srv.WECHAT_CREDS_DIR.mkdir(parents=True, exist_ok=True)
    creds_file = srv.WECHAT_CREDS_DIR / "wechat_testacc.json"
    creds_file.write_text("{}", encoding="utf-8")
    assert creds_file.exists()

    resp = await client.post("/api/wechat/logout/testacc")
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    assert not creds_file.exists()


async def test_logout_404(api):
    """POST /api/wechat/logout/{id} — unconfigured account returns 404."""
    client, _ = api
    resp = await client.post("/api/wechat/logout/nonexistent")
    assert resp.status == 404


async def test_logout_no_creds_file_200(api):
    """POST /api/wechat/logout/{id} — succeeds even if creds file doesn't exist (idempotent)."""
    client, _ = api
    await client.post("/api/wechat/accounts", json={"id": "testacc"})
    resp = await client.post("/api/wechat/logout/testacc")
    assert resp.status == 200


# ════════════════════════════════════════════════════════════════
# Tests: GET /api/wechat/status/{account_id}
# ════════════════════════════════════════════════════════════════

async def test_status_200(api):
    """GET /api/wechat/status/{id} — returns has_credentials + adapter_running flags."""
    client, _ = api
    await client.post("/api/wechat/accounts", json={"id": "testacc"})
    srv.WECHAT_CREDS_DIR.mkdir(parents=True, exist_ok=True)
    (srv.WECHAT_CREDS_DIR / "wechat_testacc.json").write_text("{}", encoding="utf-8")

    resp = await client.get("/api/wechat/status/testacc")
    assert resp.status == 200
    data = await resp.json()
    assert data["has_credentials"] is True
    assert data["adapter_running"] is False  # adapter_manager is None


async def test_status_no_creds_200(api):
    """GET /api/wechat/status/{id} — has_credentials False when no creds file."""
    client, _ = api
    await client.post("/api/wechat/accounts", json={"id": "testacc"})
    resp = await client.get("/api/wechat/status/testacc")
    assert resp.status == 200
    data = await resp.json()
    assert data["has_credentials"] is False


async def test_status_404(api):
    """GET /api/wechat/status/{id} — unconfigured account returns 404."""
    client, _ = api
    resp = await client.get("/api/wechat/status/nonexistent")
    assert resp.status == 404
