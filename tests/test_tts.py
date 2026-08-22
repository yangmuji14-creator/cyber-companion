"""Tests for the TTS 语音回复 module and Web endpoints.

Covers marker parsing, provider-config persistence, synthesis (mocked HTTP),
and the /api/voice-providers CRUD + /api/audio/synthesize endpoints.
"""

import asyncio
import io
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

import webui.server as srv
from webui.tts import (
    TTSManager,
    TTSProvider,
    TTSStore,
    parse_voice_markers,
    strip_voice_markers,
)
from tests.test_webui import FakeAppComponents


# ---- marker parsing ----

def test_parse_voice_markers_no_marker():
    display, has = parse_voice_markers("今天天气真好")
    assert display == "今天天气真好"
    assert has is False


def test_parse_voice_markers_plain():
    display, has = parse_voice_markers("[语音]宝贝，我今天特别想你~")
    assert has is True
    assert display == "宝贝，我今天特别想你~"


def test_parse_voice_markers_emotion_and_english():
    display, has = parse_voice_markers("[语音-happy]超开心的！[voice]晚上见")
    assert has is True
    assert display == "超开心的！晚上见"


def test_strip_only_markers():
    assert strip_voice_markers("[voice-sad]有点难过") == "有点难过"


# ---- store CRUD ----

def test_store_roundtrip(tmp_path):
    store = TTSStore(tmp_path)
    assert store.load_providers() == []
    store.save_providers([
        TTSProvider(name="test", api_key="sk-abc", model="tts-1", voice="alloy"),
    ])
    providers = store.load_providers()
    assert len(providers) == 1
    assert providers[0].name == "test"
    assert providers[0].api_key == "sk-abc"


def test_store_active_provider_only_enabled(tmp_path):
    store = TTSStore(tmp_path)
    store.save_providers([
        TTSProvider(name="a", enabled=False),
        TTSProvider(name="b", enabled=True),
    ])
    assert store.active_provider().name == "b"


# ---- synthesize (mocked HTTP) ----

class FakeAsyncClient:
    """Minimal httpx.AsyncClient stand-in with a canned post()."""

    def __init__(self, *, timeout=None):
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None, headers=None):
        self.calls.append((url, json, headers))
        if json is not None and json.get("boom"):
            return FakeResp(500, b"server error")
        return FakeResp(200, b"\xff\xfbMP3DATA")


class FakeResp:
    def __init__(self, status, content):
        self.status = status
        self.status_code = status
        self.content = content
        self.text = content.decode("latin1")

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(self.text)


def _patch_httpx(monkeypatch):
    """Patch the real httpx module's AsyncClient (tts.py does `import httpx`)."""
    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)


async def test_synthesize_success(monkeypatch, tmp_path):
    _patch_httpx(monkeypatch)
    store = TTSStore(tmp_path)
    store.save_providers([TTSProvider(name="p", api_key="k", base_url="https://x")])
    manager = TTSManager(store)
    data = await manager.synthesize("你好")
    assert data == b"\xff\xfbMP3DATA"


async def test_synthesize_no_provider(monkeypatch, tmp_path):
    store = TTSStore(tmp_path)
    manager = TTSManager(store)
    with pytest.raises(ValueError):
        await manager.synthesize("你好")


def _make_fixture(monkeypatch, tmp_path):
    providers = tmp_path / "tts_providers.json"
    monkeypatch.setattr(srv, "CONFIG_DIR", tmp_path)
    return providers


@pytest.fixture
async def api(monkeypatch, tmp_path):
    """Isolated TTS config dir + fake components + TestClient."""
    monkeypatch.setattr(srv, "CONFIG_DIR", tmp_path)
    components = FakeAppComponents()
    app = srv._make_app(components)
    server = TestServer(app)
    cli = TestClient(server)
    await cli.start_server()
    try:
        yield cli
    finally:
        await cli.close()


async def test_voice_providers_crud(api):
    cli = api
    # empty
    resp = await cli.get("/api/voice-providers")
    assert resp.status == 200
    assert (await resp.json())["providers"] == []

    # create
    resp = await cli.post("/api/voice-providers", json={
        "name": "mytts", "api_key": "sk-secret", "model": "tts-1", "voice": "nova",
    })
    assert resp.status == 200

    # list should mask api_key
    data = (await (await cli.get("/api/voice-providers")).json())
    assert data["providers"][0]["name"] == "mytts"
    assert data["providers"][0]["has_api_key"] is True
    assert "api_key" not in data["providers"][0]

    # duplicate -> 409
    resp = await cli.post("/api/voice-providers", json={"name": "mytts"})
    assert resp.status == 409

    # update without new key keeps old
    resp = await cli.put("/api/voice-providers/mytts", json={"voice": "onyx"})
    assert resp.status == 200
    store = srv._tts_store()
    assert store.load_providers()[0].voice == "onyx"
    assert store.load_providers()[0].api_key == "sk-secret"

    # delete
    resp = await cli.delete("/api/voice-providers/mytts")
    assert resp.status == 200
    assert (await (await cli.get("/api/voice-providers")).json())["providers"] == []


async def test_voice_providers_validation(api):
    cli = api
    resp = await cli.post("/api/voice-providers", json={"name": "  "})
    assert resp.status == 400
    resp = await cli.delete("/api/voice-providers/missing")
    assert resp.status == 404


async def test_synthesize_endpoint(api, monkeypatch, tmp_path):
    _patch_httpx(monkeypatch)
    cli = api
    # seed a provider
    await cli.post("/api/voice-providers", json={
        "name": "p1", "api_key": "k", "base_url": "https://x",
    })
    resp = await cli.get("/api/audio/synthesize", params={"text": "你好"})
    assert resp.status == 200
    body = await resp.read()
    assert body == b"\xff\xfbMP3DATA"
    assert resp.headers.get("Accept-Ranges") == "bytes"
