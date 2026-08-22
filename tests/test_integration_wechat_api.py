"""T12 Integration: WeChat account management full lifecycle.

Verifies the full account CRUD → SSE login → status → logout → delete
flow end-to-end through the real HTTP routes (T8). The weixin-ilink SDK
is ALWAYS mocked via sys.modules — no real WeChat login is ever
triggered. The fake login() calls on_qrcode + on_status_change
synchronously, then writes fake creds to save_to and returns them.

This file focuses on INTEGRATION (full lifecycle narratives), NOT
individual route unit tests. Per-route 200/400/404/409 cases are
covered by tests/test_wechat_api.py (T8). This file verifies that
the routes compose into a coherent multi-step flow.

Flows covered (per T12 plan):
1. Full lifecycle single account: create → list shows it → SSE login
   (qrcode + status + done) → creds file created → status has_credentials
   → logout → creds gone → delete → removed from config.
2. Two accounts in parallel: both created → both logged in via SSE →
   both have independent creds files → both logged out → both deleted.
3. Delete without prior logout: DELETE removes account from config AND
   deletes the creds file (auto-cleanup, T8 delete route behavior).
4. Re-login after logout: login → logout → login again succeeds and
   re-creates the creds file.

Privacy: all account IDs use placeholders (intacc1, intacc2). The fake
SDK returns placeholder creds (wxid="fake_wxid", token="fake_token").
No real WeChat accounts or credentials are referenced.
"""

import json
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from aiohttp.test_utils import TestClient, TestServer

import webui.server as srv
from tests.test_webui import FakeAppComponents


# ════════════════════════════════════════════════════════════════
# Fake weixin-ilink SDK — module-level factory (T8 pattern)
# ════════════════════════════════════════════════════════════════

_FAKE_CREDS = {"wxid": "fake_wxid", "nickname": "fake_user", "token": "fake_token"}


def _make_fake_weixin_ilink(*, fail=False):
    """Build a fake weixin_ilink module for sys.modules injection.

    Mirrors the real SDK's login() signature:
        login(save_to, on_qrcode=None, on_status_change=None) -> creds dict

    The fake invokes on_qrcode + on_status_change synchronously, writes
    fake creds to save_to, and returns them. If fail=True, login() raises
    RuntimeError (used to test SSE done{ok:false} path).

    Args:
        fail: if True, login() raises RuntimeError instead of succeeding.
    """
    fake_module = types.ModuleType("weixin_ilink")

    def fake_login(save_to, on_qrcode=None, on_status_change=None):
        if fail:
            raise RuntimeError("fake login failure")
        if on_qrcode is not None:
            on_qrcode("http://fake-qr-url")
        if on_status_change is not None:
            on_status_change("scaned")     # SDK sends "scaned" (sic)
            on_status_change("confirmed")
        # Write fake creds to save_to (mirrors real SDK behavior)
        with open(save_to, "w", encoding="utf-8") as f:
            json.dump(_FAKE_CREDS, f)
        return _FAKE_CREDS

    fake_module.login = fake_login
    return fake_module


# ════════════════════════════════════════════════════════════════
# Fixture — isolated settings + creds dir + faked components
# ════════════════════════════════════════════════════════════════


@pytest.fixture
async def wechat_api(monkeypatch, tmp_path):
    """Yield (TestClient, FakeAppComponents, tmp_path) with isolated paths.

    settings.json starts with NO wechat accounts configured (empty
    accounts array). Each test adds accounts via POST as needed.
    WECHAT_CREDS_DIR points at tmp_path/credentials so creds files are
    isolated from the real data/credentials directory.
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

    # Clear login locks from previous tests (T8 lesson #4)
    srv._wechat_login_locks.clear()

    components = FakeAppComponents()
    components.adapter_manager = None  # no AdapterManager injected

    app = srv._make_app(components)
    server = TestServer(app)
    cli = TestClient(server)
    await cli.start_server()
    try:
        yield cli, components, tmp_path
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


def _creds_path(tmp_path, account_id: str) -> Path:
    """Compute the credentials file path for an account (mirrors server logic)."""
    creds_dir = tmp_path / "credentials"
    if account_id == "default":
        return creds_dir / "wechat.json"
    return creds_dir / f"wechat_{account_id}.json"


# ════════════════════════════════════════════════════════════════
# Tests — full lifecycle flows
# ════════════════════════════════════════════════════════════════


async def test_full_lifecycle_create_login_status_logout_delete(
    wechat_api, monkeypatch,
):
    """Full lifecycle: create → list → SSE login → status → logout → delete.

    Single narrative covering all six T8 wechat endpoints in sequence
    on one account (intacc1):
    1. POST   /api/wechat/accounts           {id:"intacc1"} → 200
    2. GET    /api/wechat/accounts                       → includes intacc1
    3. GET    /api/wechat/login/intacc1/qrcode (mocked)  → SSE: qrcode +
       status(scanning) + status(confirmed) + done{ok:true} → creds file
    4. GET    /api/wechat/status/intacc1                  → has_credentials:true
    5. POST   /api/wechat/logout/intacc1                  → 200, creds gone
    6. DELETE /api/wechat/accounts/intacc1                → 200, removed
    """
    client, _components, tmp_path = wechat_api

    # 1. Create account
    resp = await client.post("/api/wechat/accounts", json={
        "id": "intacc1", "enabled": True, "auto_start": False,
    })
    assert resp.status == 200
    data = await resp.json()
    assert data["id"] == "intacc1"

    # 2. List includes intacc1
    resp = await client.get("/api/wechat/accounts")
    assert resp.status == 200
    accounts = await resp.json()
    assert any(a["id"] == "intacc1" for a in accounts)
    acc = next(a for a in accounts if a["id"] == "intacc1")
    assert acc["has_credentials"] is False  # not logged in yet

    # 3. SSE login with mocked SDK
    fake_module = _make_fake_weixin_ilink()
    monkeypatch.setitem(sys.modules, "weixin_ilink", fake_module)

    resp = await client.get("/api/wechat/login/intacc1/qrcode")
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

    # status events include scanning + confirmed
    status_events = [e[1]["status"] for e in events if e[0] == "status"]
    assert "scanning" in status_events
    assert "confirmed" in status_events

    # done event has ok:true
    done_event = next(e[1] for e in events if e[0] == "done")
    assert done_event["ok"] is True

    # Creds file created at the expected path
    creds_path = _creds_path(tmp_path, "intacc1")
    assert creds_path.exists()
    saved_creds = json.loads(creds_path.read_text(encoding="utf-8"))
    assert saved_creds["wxid"] == "fake_wxid"

    # 4. Status shows has_credentials:true
    resp = await client.get("/api/wechat/status/intacc1")
    assert resp.status == 200
    data = await resp.json()
    assert data["has_credentials"] is True
    assert data["adapter_running"] is False  # adapter_manager is None

    # 5. Logout → creds file gone
    resp = await client.post("/api/wechat/logout/intacc1")
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    assert not creds_path.exists()

    # Status now shows has_credentials:false
    resp = await client.get("/api/wechat/status/intacc1")
    assert resp.status == 200
    assert (await resp.json())["has_credentials"] is False

    # 6. Delete account → removed from config
    resp = await client.delete("/api/wechat/accounts/intacc1")
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True

    # List no longer includes intacc1
    resp = await client.get("/api/wechat/accounts")
    accounts = await resp.json()
    assert not any(a["id"] == "intacc1" for a in accounts)

    # Status now 404 (account not configured)
    resp = await client.get("/api/wechat/status/intacc1")
    assert resp.status == 404


async def test_two_accounts_full_lifecycle_in_parallel(wechat_api, monkeypatch):
    """Two accounts created → both logged in → both logged out → both deleted.

    Integration: verifies that two wechat accounts have independent
    credentials files (T4 lesson #1), independent login sessions (T8
    per-account locks), and independent lifecycle state. Account intacc1
    operations never affect intacc2 and vice versa.
    """
    client, _components, tmp_path = wechat_api

    # Create two accounts
    for acc_id in ("intacc1", "intacc2"):
        resp = await client.post("/api/wechat/accounts", json={"id": acc_id})
        assert resp.status == 200

    # Both appear in list
    resp = await client.get("/api/wechat/accounts")
    accounts = {a["id"]: a for a in await resp.json()}
    assert set(accounts.keys()) == {"intacc1", "intacc2"}
    assert all(not a["has_credentials"] for a in accounts.values())

    # Inject fake SDK once (shared across both logins)
    fake_module = _make_fake_weixin_ilink()
    monkeypatch.setitem(sys.modules, "weixin_ilink", fake_module)

    # Login both accounts via SSE
    creds_paths = {}
    for acc_id in ("intacc1", "intacc2"):
        resp = await client.get(f"/api/wechat/login/{acc_id}/qrcode")
        assert resp.status == 200
        body = await resp.text()
        events = _parse_sse_events(body)
        done_event = next(e[1] for e in events if e[0] == "done")
        assert done_event["ok"] is True

        # Independent creds files
        cp = _creds_path(tmp_path, acc_id)
        assert cp.exists()
        creds_paths[acc_id] = cp

    # Creds files are distinct paths (T4 isolation)
    assert creds_paths["intacc1"] != creds_paths["intacc2"]
    assert creds_paths["intacc1"].name == "wechat_intacc1.json"
    assert creds_paths["intacc2"].name == "wechat_intacc2.json"

    # Both have has_credentials:true
    for acc_id in ("intacc1", "intacc2"):
        resp = await client.get(f"/api/wechat/status/{acc_id}")
        assert resp.status == 200
        assert (await resp.json())["has_credentials"] is True

    # Logout intacc1 only — intacc2 unaffected
    resp = await client.post("/api/wechat/logout/intacc1")
    assert resp.status == 200
    assert not creds_paths["intacc1"].exists()
    assert creds_paths["intacc2"].exists()  # still logged in

    resp = await client.get("/api/wechat/status/intacc1")
    assert (await resp.json())["has_credentials"] is False
    resp = await client.get("/api/wechat/status/intacc2")
    assert (await resp.json())["has_credentials"] is True

    # Logout intacc2
    resp = await client.post("/api/wechat/logout/intacc2")
    assert resp.status == 200
    assert not creds_paths["intacc2"].exists()

    # Delete both
    for acc_id in ("intacc1", "intacc2"):
        resp = await client.delete(f"/api/wechat/accounts/{acc_id}")
        assert resp.status == 200

    # List is now empty
    resp = await client.get("/api/wechat/accounts")
    assert await resp.json() == []


async def test_delete_without_logout_auto_cleans_creds(wechat_api, monkeypatch):
    """DELETE account without prior logout → creds file is auto-removed.

    Integration: the DELETE route (T8) removes the account from config
    AND deletes the creds file in one shot. This is the "user forgot to
    logout but wants to remove the account" path. Verifies that delete
    is sufficient cleanup — no orphaned creds file left behind.
    """
    client, _components, tmp_path = wechat_api

    # Create + login (skip logout)
    await client.post("/api/wechat/accounts", json={"id": "intacc1"})
    fake_module = _make_fake_weixin_ilink()
    monkeypatch.setitem(sys.modules, "weixin_ilink", fake_module)

    resp = await client.get("/api/wechat/login/intacc1/qrcode")
    assert resp.status == 200
    # Drain the SSE body so the handler completes its loop and writes
    # the creds file. Without this, the handler is still streaming.
    body = await resp.text()
    done_event = next(
        e[1] for e in _parse_sse_events(body) if e[0] == "done"
    )
    assert done_event["ok"] is True
    creds_path = _creds_path(tmp_path, "intacc1")
    assert creds_path.exists()

    # DELETE directly (no logout) — should remove creds file too
    resp = await client.delete("/api/wechat/accounts/intacc1")
    assert resp.status == 200
    assert not creds_path.exists()

    # Account gone from config
    resp = await client.get("/api/wechat/accounts")
    assert await resp.json() == []

    # Status 404 (account not configured)
    resp = await client.get("/api/wechat/status/intacc1")
    assert resp.status == 404


async def test_relogin_after_logout_succeeds(wechat_api, monkeypatch):
    """Login → logout → login again re-creates creds file.

    Integration: logout removes the creds file but does NOT invalidate
    the account config. A subsequent SSE login should succeed and write
    a fresh creds file. Verifies that the per-account login lock is
    released after logout (no stuck "already in progress" state).
    """
    client, _components, tmp_path = wechat_api

    await client.post("/api/wechat/accounts", json={"id": "intacc1"})
    fake_module = _make_fake_weixin_ilink()
    monkeypatch.setitem(sys.modules, "weixin_ilink", fake_module)

    creds_path = _creds_path(tmp_path, "intacc1")

    # First login
    resp = await client.get("/api/wechat/login/intacc1/qrcode")
    assert resp.status == 200
    body = await resp.text()
    done_event = next(
        e[1] for e in _parse_sse_events(body) if e[0] == "done"
    )
    assert done_event["ok"] is True
    assert creds_path.exists()

    # Logout
    resp = await client.post("/api/wechat/logout/intacc1")
    assert resp.status == 200
    assert not creds_path.exists()

    # Login lock should be released (not stuck in "in progress")
    assert "intacc1" not in srv._wechat_login_locks or \
        not srv._wechat_login_locks["intacc1"].locked()

    # Second login succeeds
    resp = await client.get("/api/wechat/login/intacc1/qrcode")
    assert resp.status == 200
    body = await resp.text()
    done_event = next(
        e[1] for e in _parse_sse_events(body) if e[0] == "done"
    )
    assert done_event["ok"] is True
    assert creds_path.exists()

    # Creds file content is valid
    saved = json.loads(creds_path.read_text(encoding="utf-8"))
    assert saved["wxid"] == "fake_wxid"


async def test_sse_login_failure_does_not_create_creds(
    wechat_api, monkeypatch,
):
    """SDK raises during login → done{ok:false} → no creds file written.

    Integration: a failed login must not leave a partial creds file
    behind. The user can retry login after fixing the SDK issue.
    """
    client, _components, tmp_path = wechat_api

    await client.post("/api/wechat/accounts", json={"id": "intacc1"})
    fake_module = _make_fake_weixin_ilink(fail=True)
    monkeypatch.setitem(sys.modules, "weixin_ilink", fake_module)

    resp = await client.get("/api/wechat/login/intacc1/qrcode")
    assert resp.status == 200  # SSE still starts, error is in done event
    body = await resp.text()
    events = _parse_sse_events(body)
    done_event = next(e[1] for e in events if e[0] == "done")
    assert done_event["ok"] is False
    assert "error" in done_event
    assert "fake login failure" in done_event["error"]

    # No creds file created
    creds_path = _creds_path(tmp_path, "intacc1")
    assert not creds_path.exists()

    # Status shows has_credentials:false (login didn't succeed)
    resp = await client.get("/api/wechat/status/intacc1")
    assert resp.status == 200
    assert (await resp.json())["has_credentials"] is False

    # Lock is released — can retry login immediately
    assert "intacc1" not in srv._wechat_login_locks or \
        not srv._wechat_login_locks["intacc1"].locked()

    # Retry with a working SDK
    fake_module_ok = _make_fake_weixin_ilink(fail=False)
    monkeypatch.setitem(sys.modules, "weixin_ilink", fake_module_ok)

    resp = await client.get("/api/wechat/login/intacc1/qrcode")
    assert resp.status == 200
    done_event = next(
        e[1] for e in _parse_sse_events(await resp.text()) if e[0] == "done"
    )
    assert done_event["ok"] is True
    assert creds_path.exists()


async def test_default_account_uses_legacy_creds_filename(wechat_api, monkeypatch):
    """Account with id="default" → creds file is wechat.json (not wechat_default.json).

    Integration: T4 lesson #1 backward-compat — the "default" account id
    is exempt from the namespaced filename and uses the legacy
    wechat.json path. Verifies the full lifecycle works for the default
    account (which is what older installs use).
    """
    client, _components, tmp_path = wechat_api

    # Create default account
    resp = await client.post("/api/wechat/accounts", json={"id": "default"})
    assert resp.status == 200

    # Login
    fake_module = _make_fake_weixin_ilink()
    monkeypatch.setitem(sys.modules, "weixin_ilink", fake_module)

    resp = await client.get("/api/wechat/login/default/qrcode")
    assert resp.status == 200
    done_event = next(
        e[1] for e in _parse_sse_events(await resp.text()) if e[0] == "done"
    )
    assert done_event["ok"] is True

    # Creds file is wechat.json (legacy path), NOT wechat_default.json
    creds_path = _creds_path(tmp_path, "default")
    assert creds_path.name == "wechat.json"
    assert creds_path.exists()

    # Logout removes wechat.json
    resp = await client.post("/api/wechat/logout/default")
    assert resp.status == 200
    assert not creds_path.exists()

    # Delete
    resp = await client.delete("/api/wechat/accounts/default")
    assert resp.status == 200
    resp = await client.get("/api/wechat/accounts")
    assert await resp.json() == []
