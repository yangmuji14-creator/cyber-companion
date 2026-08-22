"""Tests for the 发现/朋友圈 (moments) feature.

Bootstraps the aiohttp app via `webui.server._make_app` with isolated
`_MOMENTS_PATH` and a FakeAppComponents, mirroring test_webui.py conventions.
"""

import json
import sys
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

import webui.server as srv
from tests.test_webui import FakeAppComponents


@pytest.fixture
async def api(monkeypatch, tmp_path):
    """Isolated moments store + fake components + TestClient."""
    moments_file = tmp_path / "moments.json"
    monkeypatch.setattr(srv, "_MOMENTS_PATH", moments_file)
    monkeypatch.setattr(srv, "SETTINGS_PATH", tmp_path / "settings.json")

    components = FakeAppComponents()
    components.persona_loader.add_test_persona("test_001", "测试人设")
    components.persona_loader.add_test_persona("test_002", "另一个")

    app = srv._make_app(components)
    server = TestServer(app)
    cli = TestClient(server)
    await cli.start_server()
    try:
        yield cli
    finally:
        await cli.close()


def _post(client, path, payload):
    return client.post(path, json=payload)


async def test_moments_publish_list_like_reply_delete(api):
    client = api

    # publish a user post
    resp = await _post(client, "/api/moments", {"text": "今天心情不错"})
    assert resp.status == 201
    created = (await resp.json())["moment"]
    assert created["author"] == "user"
    assert created["author_label"] == "我"

    # publish as a persona
    resp = await _post(client, "/api/moments", {"text": "我也在呢", "author": "test_001"})
    assert resp.status == 201
    persona_moment = (await resp.json())["moment"]
    assert persona_moment["author"] == "test_001"
    assert persona_moment["author_label"] == "测试人设"

    # list: newest first
    resp = await client.get("/api/moments")
    assert resp.status == 200
    data = await resp.json()
    assert len(data["moments"]) == 2
    assert data["moments"][0]["id"] == persona_moment["id"]

    # like + unlike
    mid = created["id"]
    resp = await client.post(f"/api/moments/{mid}/like")
    assert resp.status == 200
    assert (await resp.json())["added"] is True
    resp = await client.delete(f"/api/moments/{mid}/like")
    assert (await resp.json())["removed"] is True

    # reply
    resp = await _post(client, f"/api/moments/{mid}/replies", {"text": "赞一个"})
    assert resp.status == 201
    reply = (await resp.json())["reply"]
    assert reply["author_label"] == "我"

    # delete reply
    resp = await client.delete(f"/api/moments/{mid}/replies/{reply['id']}")
    assert resp.status == 200

    # delete moment
    resp = await client.delete(f"/api/moments/{mid}")
    assert resp.status == 200
    resp = await client.get("/api/moments")
    assert len((await resp.json())["moments"]) == 1


async def test_moments_validation(api):
    client = api
    # empty text rejected
    resp = await _post(client, "/api/moments", {"text": "   "})
    assert resp.status == 400
    # bad moment id on delete
    resp = await client.delete("/api/moments/nope")
    assert resp.status == 400
    # reply to missing moment -> 404
    resp = await _post(client, "/api/moments/mom_000000000000/replies", {"text": "hi"})
    assert resp.status == 404


async def test_moments_personas_list(api):
    client = api
    resp = await client.get("/api/moments/personas")
    assert resp.status == 200
    personas = (await resp.json())["personas"]
    assert any(p["id"] == "test_001" for p in personas)
