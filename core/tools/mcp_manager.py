"""MCP Manager — 多 Server 管理器 [稳定性加固版]

- 工具名冲突检测 + 自动加命名空间前缀
- 并行连接 + 独立错误隔离
- 动态工具刷新
- 连接状态仪表盘
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from loguru import logger

from core.config import RESOURCE_DIR
from core.runtime import resolve_runtime_command
from core.tools.mcp_client import MCPClient, MCPConfig, MCPTool


class MCPManager:
    """MCP Server 统一管理器"""

    def __init__(self):
        self._clients: dict[str, MCPClient] = {}
        self._tool_index: dict[str, str] = {}
        self._conflicts: set[str] = set()
        self._connected = False

    async def load_and_connect(self, config_dir: str | Path) -> int:
        config_path = Path(config_dir) / "mcp_servers.json"
        if not config_path.exists():
            return 0

        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"MCP config load failed: {e}")
            return 0

        servers = [s for s in data.get("servers", []) if s.get("enabled", True)]
        if not servers:
            return 0

        tasks = []
        for srv in servers:
            configured_cwd = str(srv.get("cwd") or "").strip()
            if configured_cwd:
                cwd_path = Path(configured_cwd)
                cwd = str(cwd_path if cwd_path.is_absolute() else (RESOURCE_DIR / cwd_path).resolve())
            else:
                # Built-in server scripts use relative paths and should resolve
                # against packaged resources, never the user's shell cwd.
                cwd = str(RESOURCE_DIR)
            config = MCPConfig(
                name=srv["name"], command=resolve_runtime_command(srv["command"]),
                args=srv.get("args", []), env=srv.get("env", {}),
                cwd=cwd,
                auto_reconnect=srv.get("auto_reconnect", True),
                max_reconnect_attempts=srv.get("max_reconnect_attempts", 10),
                reconnect_base_delay=srv.get("reconnect_base_delay", 1.0),
                reconnect_max_delay=srv.get("reconnect_max_delay", 60.0),
                reconnect_backoff=srv.get("reconnect_backoff", 2.0),
                startup_timeout=srv.get("startup_timeout", 30.0),
                operation_timeout=srv.get("operation_timeout", 60.0),
            )
            client = MCPClient(config)
            self._clients[config.name] = client
            tasks.append(self._connect_one(client))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        connected = sum(1 for r in results if r is True)
        if connected > 0:
            await self._discover_all_tools()

        logger.info(f"MCP: {connected}/{len(tasks)} servers, {self.tools_count} tools, {len(self._conflicts)} namespaced")
        self._connected = connected > 0
        return connected

    async def _connect_one(self, client: MCPClient) -> bool:
        try:
            return await client.connect()
        except Exception as e:
            logger.warning(f"MCP [{client.config.name}]: {e}")
            return False

    # ── 单服务器控制 (供 webui 的 connect/test/refresh/disconnect/tools 端点使用) ──

    def _build_client(self, srv: dict) -> MCPClient:
        """根据配置字典构造客户端, 与 load_and_connect 逻辑保持一致。"""
        name = str(srv.get("name") or "").strip()
        configured_cwd = str(srv.get("cwd") or "").strip()
        if configured_cwd:
            cwd_path = Path(configured_cwd)
            cwd = str(cwd_path if cwd_path.is_absolute() else (RESOURCE_DIR / cwd_path).resolve())
        else:
            cwd = str(RESOURCE_DIR)
        config = MCPConfig(
            name=name, command=resolve_runtime_command(str(srv.get("command") or "")),
            args=srv.get("args", []), env=srv.get("env", {}),
            cwd=cwd,
            auto_reconnect=srv.get("auto_reconnect", True),
            max_reconnect_attempts=srv.get("max_reconnect_attempts", 10),
            reconnect_base_delay=srv.get("reconnect_base_delay", 1.0),
            reconnect_max_delay=srv.get("reconnect_max_delay", 60.0),
            reconnect_backoff=srv.get("reconnect_backoff", 2.0),
            startup_timeout=srv.get("startup_timeout", 30.0),
            operation_timeout=srv.get("operation_timeout", 60.0),
        )
        return MCPClient(config)

    async def _rediscover_for(self, name: str) -> None:
        """刷新单个服务器的工具索引 (保持 _tool_index 与其他服务器一致)。"""
        client = self._clients.get(name)
        if client is None or not client.is_connected:
            return
        try:
            tools = await client.list_tools()
        except Exception as e:
            logger.warning(f"MCP [{name}]: rediscover failed: {e}")
            return
        # 移除该服务器旧的工具映射, 再重新建立
        self._tool_index = {k: v for k, v in self._tool_index.items() if v != name}
        for tool in tools:
            self._tool_index[tool.name] = name

    async def test_server(self, srv: dict) -> dict:
        """测试单个 MCP 服务器连通性 (不常驻连接)。"""
        client = self._build_client(srv)
        try:
            connected = await client.connect()
            if connected:
                await client.disconnect()
            return {"ok": connected, "connected": connected,
                    "message": "连通正常" if connected else "连接失败"}
        except Exception as e:
            return {"ok": False, "error": str(e)}
        finally:
            await client.disconnect()

    async def connect_server(self, srv: dict) -> bool:
        """连接单个 MCP 服务器并注册到管理器的客户端池。"""
        name = str(srv.get("name") or "").strip()
        existing = self._clients.get(name)
        if existing is not None and existing.is_connected:
            return True
        client = self._build_client(srv)
        connected = await client.connect()
        if connected:
            self._clients[name] = client
            await self._discover_all_tools()
            self._connected = self.connected_count > 0
        return connected

    async def disconnect_server(self, srv: dict) -> None:
        """断开单个 MCP 服务器并移除。"""
        name = str(srv.get("name") or "").strip()
        client = self._clients.pop(name, None)
        if client is not None:
            await client.disconnect()
            self._tool_index = {k: v for k, v in self._tool_index.items() if v != name}
            self._connected = self.connected_count > 0

    async def refresh_server(self, srv: dict) -> int:
        """刷新单个 MCP 服务器: 未连接则连接, 然后重新发现工具。"""
        name = str(srv.get("name") or "").strip()
        client = self._clients.get(name)
        if client is None or not client.is_connected:
            client = self._build_client(srv)
            connected = await client.connect()
            if not connected:
                return 0
            self._clients[name] = client
        await self._rediscover_for(name)
        self._connected = self.connected_count > 0
        return sum(1 for k, v in self._tool_index.items() if v == name)

    def get_server_tools(self, name: str) -> list["MCPTool"]:
        """返回单个 MCP 服务器已发现的工具列表。"""
        client = self._clients.get(name)
        if client is None or not client.is_connected:
            return []
        return list(client.get_tools())

    async def disconnect_all(self) -> None:
        self._connected = False
        tasks = [c.disconnect() for c in self._clients.values()]
        await asyncio.gather(*tasks, return_exceptions=True)
        self._clients.clear()
        self._tool_index.clear()
        self._conflicts.clear()

    # ── 工具发现 + 冲突检测 ──

    async def _discover_all_tools(self) -> None:
        tasks = {n: asyncio.create_task(c.list_tools()) for n, c in self._clients.items() if c.is_connected}
        if not tasks:
            return

        all_tools: dict[str, list[MCPTool]] = {}
        for name, task in tasks.items():
            try:
                tools = await task
                all_tools[name] = tools
            except Exception as e:
                logger.warning(f"MCP [{name}]: discovery failed: {e}")

        name_map: dict[str, list[str]] = {}
        for srv_name, tools in all_tools.items():
            for tool in tools:
                name_map.setdefault(tool.name, []).append(srv_name)

        self._tool_index.clear()
        self._conflicts.clear()
        for tool_name, servers in name_map.items():
            if len(servers) > 1:
                for srv in servers:
                    self._tool_index[f"{srv}__{tool_name}"] = srv
                self._conflicts.add(tool_name)
                logger.warning(f"MCP: tool '{tool_name}' conflicts across {servers} → prefixed")
            else:
                self._tool_index[tool_name] = servers[0]

    async def refresh_tools(self) -> int:
        await self._discover_all_tools()
        return len(self._tool_index)

    # ── 工具查询 ──

    def get_all_tools(self) -> list[MCPTool]:
        all_tools = []
        for client in self._clients.values():
            if client.is_connected:
                for tool in client.get_tools():
                    if tool.name in self._conflicts:
                        all_tools.append(MCPTool(
                            name=f"{tool.server_name}__{tool.name}",
                            description=f"[{tool.server_name}] {tool.description}",
                            parameters=tool.parameters,
                            server_name=tool.server_name,
                        ))
                    else:
                        all_tools.append(tool)
        return all_tools

    def get_tool_by_name(self, name: str) -> MCPTool | None:
        for client in self._clients.values():
            for tool in client.get_tools():
                if tool.name == name:
                    return tool

        if "__" in name:
            parts = name.split("__", 1)
            client = self._clients.get(parts[0])
            if client:
                for tool in client.get_tools():
                    if tool.name == parts[1]:
                        return tool
        return None

    # ── 工具调用 ──

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        server_name = self._tool_index.get(name)
        actual_name = name

        if not server_name and "__" in name:
            parts = name.split("__", 1)
            if parts[0] in self._clients:
                server_name = parts[0]
                actual_name = parts[1]

        if not server_name:
            return f"[MCP] tool not found: {name}"
        client = self._clients.get(server_name)
        if not client:
            return f"[MCP] server '{server_name}' not connected"
        return await client.call_tool(actual_name, arguments)

    # ── Prompt ──

    def get_tools_prompt(self) -> str:
        tools = self.get_all_tools()
        if not tools:
            return ""
        lines = ["【MCP 扩展工具】", "调用格式：【工具调用：工具名(参数名=\"值\")】", ""]
        for tool in tools:
            props = tool.parameters.get("properties", {})
            req_list = tool.parameters.get("required", [])
            params = [f"  - {p}: {i.get('description','')} {'(必填)' if p in req_list else '(可选)'}"
                      for p, i in props.items()]
            lines.append(f"- [{tool.server_name}] {tool.name}: {tool.description}")
            if params: lines.extend(params)
        return "\n".join(lines)

    # ── 状态 ──

    def get_status(self) -> dict[str, Any]:
        return {n: {"state": c.state.value, "connected": c.is_connected, "tools": len(c.get_tools())}
                for n, c in self._clients.items()}

    @property
    def connected_count(self) -> int:
        return sum(1 for c in self._clients.values() if c.is_connected)

    @property
    def tools_count(self) -> int:
        return len(self._tool_index)

    @property
    def is_any_connected(self) -> bool:
        return self._connected
