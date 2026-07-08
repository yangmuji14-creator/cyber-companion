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
            config = MCPConfig(
                name=srv["name"], command=srv["command"],
                args=srv.get("args", []), env=srv.get("env", {}),
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
