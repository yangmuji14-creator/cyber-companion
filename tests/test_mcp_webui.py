"""Tests for the MCP 扩展 (servers) settings endpoints.

Bootstraps the aiohttp app via `webui.server._make_app` with isolated
`_MCP_SERVERS_PATH` (and moments path to avoid touching real data), mirroring
test_webui.py / test_moments.py conventions. Per-server control endpoints are
tested by injecting a fake mcp_manager onto FakeAppComponents.
"""

import sys
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

import webui.server as srv
from tests.test_webui import FakeAppComponents


class FakeMCPManager:
    """Mock MCPManager answering the per-server control endpoints."""

    def __init__(self):
        self.connected = {"fs": True}
        self.tools = {"fs": ["read", "write"]}

    async def test_server(self, srv_cfg):
        if srv_cfg.get("name") == "fail":
            return {"ok": False, "error": "连接失败"}
        return {"ok": True, "tools": 2, "tools_list": ["read", "write"]}

    async def connect_server(self, srv_cfg):
        self.connected[srv_cfg["name"]] = True
        return True

    async def disconnect_server(self, srv_cfg):
        self.connected[srv_cfg["name"]] = False

    async def refresh_server(self, srv_cfg):
        return len(self.tools.get(srv_cfg["name"], []))

    def get_server_tools(self, name):
        if name != "fs":
            return []
        return [
            type("Tool", (), {"name": n, "description": "d"})()
            for n in self.tools.get(name, [])
        ]


@pytest.fixture
async def api(monkeypatch, tmp_path):
    monkeypatch.setattr(srv, "_MCP_SERVERS_PATH", tmp_path / "mcp_servers.json")
    monkeypatch.setattr(srv, "_MOMENTS_PATH", tmp_path / "moments.json")
    monkeypatch.setattr(srv, "SETTINGS_PATH", tmp_path / "settings.json")

    components = FakeAppComponents()
    components.mcp_manager = FakeMCPManager()
    app = srv._make_app(components)
    server = TestServer(app)
    cli = TestClient(server)
    await cli.start_server()
    try:
        yield cli
    finally:
        await cli.close()


async def test_mcp_list_empty(api):
    client = api
    resp = await client.get("/api/mcp/servers")
    assert resp.status == 200
    assert (await resp.json())["servers"] == []


async def test_mcp_add_list_update_delete(api):
    client = api

    body = {"name": "fs", "command": "npx", "args": ["-y", "@mcp/filesystem"], "env": {"K": "V"}}
    resp = await client.post("/api/mcp/servers", json=body)
    assert resp.status == 201
    server = (await resp.json())["server"]
    assert server["name"] == "fs"
    assert server["command"] == "npx"
    assert server["env"] == {"K": "V"}

    resp = await client.post("/api/mcp/servers", json=body)
    assert resp.status == 409

    resp = await client.get("/api/mcp/servers")
    servers = (await resp.json())["servers"]
    assert len(servers) == 1
    assert servers[0]["name"] == "fs"

    resp = await client.put("/api/mcp/servers/fs", json={"command": "npx", "args": ["-y", "other"]})
    assert resp.status == 200
    assert (await resp.json())["server"]["args"] == ["-y", "other"]

    resp = await client.put("/api/mcp/servers/fs", json={"command": "x", "evil": "boom", "env": {"A": "1"}})
    assert resp.status == 200
    updated = (await resp.json())["server"]
    assert "evil" not in updated
    assert updated["env"] == {"A": "1"}

    resp = await client.delete("/api/mcp/servers/fs")
    assert resp.status == 200
    resp = await client.delete("/api/mcp/servers/fs")
    assert resp.status == 404


async def test_mcp_validation(api):
    client = api
    resp = await client.post("/api/mcp/servers", json={"name": "", "command": ""})
    assert resp.status == 400
    resp = await client.post("/api/mcp/servers", json={"name": "a", "command": ""})
    assert resp.status == 400


async def test_mcp_per_server_endpoints(api):
    client = api
    # seed one server
    body = {"name": "fs", "command": "npx"}
    await client.post("/api/mcp/servers", json=body)

    # test connection
    resp = await client.post("/api/mcp/servers/fs/test")
    assert resp.status == 200
    assert (await resp.json())["ok"] is True
    assert (await resp.json())["tools"] == 2

    # test missing server -> 404
    resp = await client.post("/api/mcp/servers/nope/test")
    assert resp.status == 404

    # connect / disconnect / refresh
    resp = await client.post("/api/mcp/servers/fs/connect")
    assert resp.status == 200
    assert (await resp.json())["connected"] is True

    resp = await client.post("/api/mcp/servers/fs/refresh")
    assert resp.status == 200
    assert (await resp.json())["tools"] == 2

    resp = await client.post("/api/mcp/servers/fs/disconnect")
    assert resp.status == 200

    # tools list
    resp = await client.get("/api/mcp/servers/fs/tools")
    assert resp.status == 200
    names = [t["name"] for t in (await resp.json())["tools"]]
    assert names == ["read", "write"]
