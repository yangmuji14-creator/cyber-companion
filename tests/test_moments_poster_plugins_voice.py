"""Tests for AI auto-poster and plugin catalog endpoints.

Bootstraps the aiohttp app via `webui.server._make_app` with isolated settings
storage and a FakeAppComponents, mirroring test_moments.py conventions.
"""

import asyncio
import json
import sys

import pytest
from aiohttp.test_utils import TestClient, TestServer

import webui.server as srv
from webui.moments_poster import MomentsAutoPoster, load_poster_config
from tests.test_webui import FakeAppComponents


@pytest.fixture
async def api(monkeypatch, tmp_path):
    """Isolated settings + moments store + fake components + TestClient."""
    moments_file = tmp_path / "moments.json"
    monkeypatch.setattr(srv, "_MOMENTS_PATH", moments_file)
    monkeypatch.setattr(srv, "SETTINGS_PATH", tmp_path / "settings.json")

    components = FakeAppComponents()
    components.persona_loader.add_test_persona("test_001", "测试人设")

    app = srv._make_app(components)
    server = TestServer(app)
    cli = TestClient(server)
    await cli.start_server()
    try:
        yield cli, components
    finally:
        await cli.close()


# ── ① AI 自动发朋友圈 ──

def test_load_poster_config_defaults():
    cfg = load_poster_config({})
    assert cfg["enabled"] is False
    assert cfg["interval_minutes"] == 180
    assert cfg["persona_id"] == ""


def test_load_poster_config_overrides_and_clamps():
    raw = {"advanced": {"moments_auto_poster": {
        "enabled": True, "interval_minutes": "10",
        "persona_id": "test_001", "active_start": 25, "active_end": -3,
    }}}
    cfg = load_poster_config(raw)
    assert cfg["enabled"] is True
    assert cfg["interval_minutes"] == 10
    assert cfg["persona_id"] == "test_001"
    assert cfg["active_start"] == 23
    assert cfg["active_end"] == 0


async def test_auto_poster_config_get_put(api):
    cli, components = api
    resp = await cli.get("/api/moments/auto/config")
    assert resp.status == 200
    data = await resp.json()
    assert data["config"]["enabled"] is False
    assert any(p["id"] == "test_001" for p in data["personas"])

    resp = await cli.put(
        "/api/moments/auto/config",
        json={"enabled": True, "interval_minutes": 60, "persona_id": "test_001"},
    )
    assert resp.status == 200
    saved = (await resp.json())["config"]
    assert saved["enabled"] is True
    assert saved["interval_minutes"] == 60
    assert saved["persona_id"] == "test_001"

    # persisted to settings.json
    got = json.loads(srv.SETTINGS_PATH.read_text(encoding="utf-8"))
    assert got["advanced"]["moments_auto_poster"]["interval_minutes"] == 60


async def test_auto_poster_publish_off_respects_disabled(api, monkeypatch):
    cli, components = api
    published = []
    saver = lambda m: published.append(m) or m  # noqa: E731

    poster = MomentsAutoPoster(
        saver=saver, get_settings=srv._load_settings, generate_fn=None,
    )
    components.moments_poster = poster
    # default config disabled -> manual publish returns 400
    resp = await cli.post("/api/moments/auto/publish")
    assert resp.status == 400
    assert published == []


async def test_auto_poster_publish_writes_moment(api, monkeypatch):
    cli, components = api
    # enable + pick persona, reset poster interval
    await cli.put(
        "/api/moments/auto/config",
        json={"enabled": True, "persona_id": "test_001"},
    )
    poster = MomentsAutoPoster(
        saver=None,  # replaced below
        get_settings=srv._load_settings,
        generate_fn=None,
    )
    # wire a real saver writing to the isolated moments store
    def real_saver(moment):
        now = srv._moment_now_iso()
        record = {
            "id": srv._new_moment_id(),
            "author": moment.get("author", ""),
            "timestamp": now,
            "text": moment.get("text", ""),
            "likes": [],
            "replies": [],
        }
        moments = srv._load_moments()
        moments.insert(0, record)
        srv._save_moments(moments)
        return record

    poster._saver = real_saver
    components.moments_poster = poster
    poster._last_posted_at = None

    resp = await cli.post("/api/moments/auto/publish")
    assert resp.status == 200

    # moment persisted
    moments = srv._load_moments()
    assert len(moments) == 1
    assert moments[0]["author"] == "test_001"
    assert moments[0]["text"]


async def test_auto_poster_publish_llm_generate_used(api, monkeypatch):
    cli, components = api
    await cli.put(
        "/api/moments/auto/config",
        json={"enabled": True, "persona_id": "test_001"},
    )
    calls = []

    async def gen(system_prompt, user_prompt, max_tokens=120, temperature=0.95):
        calls.append(system_prompt)
        return "今天阳光很好，出去走了走。"

    poster = MomentsAutoPoster(
        saver=lambda m: None, get_settings=srv._load_settings, generate_fn=gen,
    )
    components.moments_poster = poster
    poster._last_posted_at = None
    resp = await cli.post("/api/moments/auto/publish")
    assert resp.status == 200
    assert calls, "LLM generator should be invoked"


async def test_auto_poster_run_loop_stops_cleanly(monkeypatch):
    """run() must not raise (regression: asyncio import was missing)."""
    calls = {"n": 0}
    poster_ref = {}

    async def fake_sleep(_seconds):
        calls["n"] += 1
        poster_ref["p"]._stop = True  # exit the loop on next iteration check

    monkeypatch.setattr("asyncio.sleep", fake_sleep)
    poster = MomentsAutoPoster(
        saver=lambda m: None,
        get_settings=lambda: {},  # disabled -> publish_once returns False fast
        generate_fn=None,
    )
    poster_ref["p"] = poster
    await poster.run(poll_seconds=1)  # completes normally, no NameError
    assert calls["n"] >= 1


# ── ② 插件管理 ──

async def test_plugins_builtin_list(api):
    cli, components = api
    resp = await cli.get("/api/plugins")
    assert resp.status == 200
    data = await resp.json()
    names = {p["name"] for p in data["plugins"] if p["source"] == "builtin"}
    assert "clock" in names
    assert "note" in names
    assert "translate" in names
    assert data["builtin_count"] >= 6
    # FakeAppComponents has no mcp_manager -> mcp_count 0, status None
    assert data["mcp_count"] == 0
    # every entry has an id-like name + description
    for p in data["plugins"]:
        assert p["name"]
        assert "description" in p
