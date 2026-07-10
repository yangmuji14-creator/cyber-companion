"""MCP Client — MCP 协议客户端 (JSON-RPC over stdio) [稳定性加固版]

实现 MCP (Model Context Protocol) 客户端：
- 进程健康监控 + 指数退避自动重连
- 分级超时（启动/操作/空闲）
- 协议版本协商 + 错误码映射
- 缓冲区保护 + 乱序消息处理
- 线程安全的请求ID

用法:
    config = MCPConfig(name="filesystem", command="npx", args=["-y", "@modelcontextprotocol/server-filesystem"])
    client = MCPClient(config)
    if await client.connect():
        tools = await client.list_tools()
        result = await client.call_tool("read_file", {"path": "/tmp/x.txt"})
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from loguru import logger


# ── 配置 ──

@dataclass
class MCPConfig:
    """MCP Server 配置 — 对齐官方 StdioServerParameters"""
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    enabled: bool = True

    # 进程控制
    cwd: str = ""                         # 工作目录
    encoding: str = "utf-8"               # 通信编码
    encoding_errors: str = "replace"       # 编码错误处理

    # 连接策略
    auto_reconnect: bool = True
    max_reconnect_attempts: int = 10
    reconnect_base_delay: float = 1.0
    reconnect_max_delay: float = 60.0
    reconnect_backoff: float = 2.0

    # 超时（秒）
    startup_timeout: float = 30.0
    operation_timeout: float = 60.0
    idle_timeout: float = 300.0


# ── 安全环境变量继承（对齐官方 MCP SDK）──
_SAFE_ENV_VARS = {
    "PATH", "HOME", "USER", "USERPROFILE", "TMP", "TEMP", "TMPDIR",
    "SYSTEMROOT", "APPDATA", "LOCALAPPDATA",
    "LANG", "LC_ALL", "PYTHONPATH", "NODE_PATH", "JAVA_HOME",
}


def _safe_environment() -> dict[str, str]:
    """返回可安全继承的环境变量（对齐 get_default_environment）"""
    env = {}
    for key in _SAFE_ENV_VARS:
        value = os.environ.get(key)
        if value:
            env[key] = value
    return env


class MCPState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    INITIALIZING = "initializing"
    READY = "ready"
    ERROR = "error"


# ── 异常 ──

class MCPError(Exception):
    """MCP 基础异常"""
    def __init__(self, message: str, server_name: str = "", code: int = -1):
        super().__init__(f"[{server_name}] {message}" if server_name else message)
        self.server_name = server_name
        self.code = code


class MCPConnectionError(MCPError):
    """连接异常"""


class MCPTimeoutError(MCPError):
    """超时异常"""


class MCPProtocolError(MCPError):
    """协议异常（版本不匹配/格式错误）"""


class MCPToolError(MCPError):
    """工具执行异常"""


# JSON-RPC 错误码映射
_MCP_ERROR_MAP: dict[int, str] = {
    -32700: "Parse error",
    -32600: "Invalid Request",
    -32601: "Method not found",
    -32602: "Invalid params",
    -32603: "Internal error",
    -32000: "Server error",
}


# ── 工具定义 ──

@dataclass
class MCPTool:
    name: str
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    server_name: str = ""

    def to_prompt_format(self) -> str:
        props = self.parameters.get("properties", {})
        req_list = self.parameters.get("required", [])
        param_lines = []
        for pname, pinfo in props.items():
            req = "（必填）" if pname in req_list else "（可选）"
            param_lines.append(f"    - {pname}: {pinfo.get('description', '')} {req}")
        param_str = "\n".join(param_lines) if param_lines else "    无参数"
        return f"- {self.name}: {self.description}\n{param_str}"


# ── 主客户端 ──

class MCPClient:
    """MCP 协议客户端 [加固版]

    特性：
    - 指数退避重连 + 最大尝试次数
    - 分级超时（启动/操作/空闲）
    - 进程存活检测（心跳 + poll）
    - 缓冲区安全保护
    - 协议版本协商 + 结构化错误
    """

    MAX_MESSAGE_SIZE = 4 * 1024 * 1024   # 4MB
    MAX_BUFFER_SIZE = 16 * 1024 * 1024   # 16MB 缓冲区上限
    PROTOCOL_VERSION = "2024-11-05"
    HEARTBEAT_INTERVAL = 15.0            # 心跳间隔（ping）

    def __init__(self, config: MCPConfig):
        self.config = config
        self.state = MCPState.DISCONNECTED
        self._process: subprocess.Popen | None = None
        self._request_id = 0
        self._request_lock = asyncio.Lock()
        self._pending: dict[int, asyncio.Future] = {}
        self._reader_task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._reconnect_task: asyncio.Task | None = None
        self._server_capabilities: dict[str, Any] = {}
        self._tools: list[MCPTool] = []
        self._reconnect_attempts = 0
        self._last_activity = 0.0
        self._server_info: dict[str, Any] = {}

    # ── 连接生命周期 ──

    async def connect(self) -> bool:
        """启动进程 + 初始化协议握手"""
        if self.state in (MCPState.CONNECTING, MCPState.READY):
            return self.state == MCPState.READY

        self.state = MCPState.CONNECTING

        try:
            # 1. 启动进程
            await self._spawn_process()

            # 2. 协议握手
            await self._initialize_handshake()

            self.state = MCPState.READY
            self._reconnect_attempts = 0
            self._last_activity = time.time()

            logger.info(
                f"MCP [{self.config.name}]: ready — "
                f"{self._server_info.get('name', '?')} "
                f"v{self._server_info.get('version', '?')}"
            )

            # 3. 启动心跳
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            return True

        except Exception as e:
            logger.warning(f"MCP [{self.config.name}]: connect failed: {e}")
            self.state = MCPState.ERROR
            self._cleanup()
            if self.config.auto_reconnect:
                self._start_reconnect()
            return False

    async def disconnect(self) -> None:
        """优雅断开"""
        self.state = MCPState.DISCONNECTED
        self._cancel_tasks()
        self._cleanup()
        self._tools.clear()
        logger.info(f"MCP [{self.config.name}]: disconnected")

    # ── 进程管理 ──

    async def _spawn_process(self) -> None:
        """启动子进程 — 安全环境继承 + cwd 支持"""
        env = _safe_environment()
        env.update(self.config.env)

        popen_kwargs = {
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "env": env,
            "text": False,
            "bufsize": 0,
        }
        if self.config.cwd:
            popen_kwargs["cwd"] = self.config.cwd
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        try:
            self._process = subprocess.Popen(
                [self.config.command] + self.config.args,
                **popen_kwargs,
            )

            # 短暂等待进程启动
            await asyncio.sleep(0.2)
            if self._process.poll() is not None:
                stderr_data = self._process.stderr.read().decode("utf-8", errors="replace") if self._process.stderr else ""
                raise MCPConnectionError(
                    f"process exited immediately (code={self._process.returncode}): {stderr_data[:200]}",
                    self.config.name,
                )

            self._reader_task = asyncio.create_task(self._read_loop())

        except FileNotFoundError:
            raise MCPConnectionError(
                f"command not found: {self.config.command}",
                self.config.name,
            )
        except MCPConnectionError:
            raise
        except Exception as e:
            raise MCPConnectionError(str(e), self.config.name)

    async def _initialize_handshake(self) -> None:
        """MCP 初始化握手"""
        try:
            result = await asyncio.wait_for(
                self._send_request("initialize", {
                    "protocolVersion": self.PROTOCOL_VERSION,
                    "clientInfo": {
                        "name": "cyber-companion",
                        "version": "3.3.0",
                    },
                    "capabilities": {
                        "tools": {},
                    },
                }),
                timeout=self.config.startup_timeout,
            )

            # 协议版本检查
            server_ver = result.get("protocolVersion", "")
            if not server_ver:
                raise MCPProtocolError("server did not report protocolVersion", self.config.name)

            self._server_capabilities = result.get("capabilities", {})
            self._server_info = result.get("serverInfo", {})

            # 发送 initialized 通知（2024-11-05 版本需要）
            await self._send_notification("notifications/initialized", {})

        except MCPError:
            raise
        except asyncio.TimeoutError:
            raise MCPTimeoutError("initialize handshake timed out", self.config.name)
        except Exception as e:
            raise MCPConnectionError(str(e), self.config.name)

    def _cleanup(self) -> None:
        """彻底清理进程资源"""
        self._cancel_tasks()

        # 取消所有 pending 请求
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(MCPConnectionError("connection closed", self.config.name))
        self._pending.clear()

        if self._process:
            p = self._process
            self._process = None
            try:
                if p.stdin: p.stdin.close()
                if p.stdout: p.stdout.close()
                if p.stderr: p.stderr.close()
            except Exception:
                pass
            try:
                if os.name == "nt":
                    p.kill()
                else:
                    p.send_signal(signal.SIGTERM)
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    p.kill()
                    p.wait(timeout=3)
                except Exception:
                    pass
            except Exception:
                pass

    def _cancel_tasks(self) -> None:
        """取消后台任务"""
        for task in (self._reader_task, self._heartbeat_task, self._reconnect_task):
            if task and not task.done():
                task.cancel()
        self._reader_task = None
        self._heartbeat_task = None

    # ── 重连逻辑 ──

    def _start_reconnect(self) -> None:
        """启动重连任务（去重：已有则跳过；auto_reconnect=False 则忽略）"""
        if not self.config.auto_reconnect:
            return
        if self._reconnect_task and not self._reconnect_task.done():
            return
        self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    async def _reconnect_loop(self) -> None:
        """指数退避重连循环"""
        while self.state == MCPState.ERROR and self.config.auto_reconnect:
            max_attempts = self.config.max_reconnect_attempts
            if max_attempts > 0 and self._reconnect_attempts >= max_attempts:
                logger.error(
                    f"MCP [{self.config.name}]: max reconnect attempts ({max_attempts}) reached, giving up"
                )
                self.state = MCPState.DISCONNECTED
                return

            self._reconnect_attempts += 1
            delay = min(
                self.config.reconnect_base_delay * (self.config.reconnect_backoff ** (self._reconnect_attempts - 1)),
                self.config.reconnect_max_delay,
            )
            logger.info(
                f"MCP [{self.config.name}]: reconnect #{self._reconnect_attempts} in {delay:.0f}s"
            )
            await asyncio.sleep(delay)

            if await self.connect():
                return  # 连接成功，退出循环

        if self.state == MCPState.ERROR:
            self.state = MCPState.DISCONNECTED

    # ── 心跳监控 ──

    async def _heartbeat_loop(self) -> None:
        """心跳循环：检测进程存活 + 空闲断开"""
        while self.state == MCPState.READY:
            await asyncio.sleep(self.HEARTBEAT_INTERVAL)

            # 进程存活检查
            if self._process and self._process.poll() is not None:
                rc = self._process.returncode if self._process else None
                logger.warning(f"MCP [{self.config.name}]: process died (code={rc})")
                self.state = MCPState.ERROR
                self._cleanup()
                if self.config.auto_reconnect:
                    self._start_reconnect()
                return

            # 空闲超时
            if self.config.idle_timeout > 0:
                idle = time.time() - self._last_activity
                if idle > self.config.idle_timeout:
                    logger.info(f"MCP [{self.config.name}]: idle timeout ({idle:.0f}s), disconnecting")
                    await self.disconnect()
                    return

    # ── JSON-RPC 通信 ──

    async def _get_next_id(self) -> int:
        """线程安全的请求ID生成"""
        async with self._request_lock:
            self._request_id += 1
            return self._request_id

    async def _send_request(self, method: str, params: dict | None = None) -> Any:
        """发送请求，等待响应"""
        rid = await self._get_next_id()
        request = {
            "jsonrpc": "2.0",
            "id": rid,
            "method": method,
            "params": params or {},
        }

        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[rid] = future

        try:
            await self._write_message(request)
        except Exception as e:
            self._pending.pop(rid, None)
            raise MCPConnectionError(f"write failed: {e}", self.config.name)

        try:
            timeout = self._get_timeout(method)
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(rid, None)
            raise MCPTimeoutError(f"{method} timed out ({timeout}s)", self.config.name)
        except MCPError:
            self._pending.pop(rid, None)
            raise

    async def _send_notification(self, method: str, params: dict | None = None) -> None:
        """发送通知（无响应）"""
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
        }
        await self._write_message(notification)

    async def _write_message(self, message: dict) -> None:
        """写入消息到子进程 stdin"""
        p = self._process
        if not p or not p.stdin or p.poll() is not None:
            raise MCPConnectionError("process not running", self.config.name)

        body = json.dumps(message, ensure_ascii=False)
        body_bytes = body.encode("utf-8")
        data = f"Content-Length: {len(body_bytes)}\r\n\r\n".encode("utf-8") + body_bytes

        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, self._sync_write, p, data)
        except BrokenPipeError:
            raise MCPConnectionError("stdin pipe broken", self.config.name)
        except Exception as e:
            raise MCPConnectionError(f"stdin write error: {e}", self.config.name)

    @staticmethod
    def _sync_write(process: subprocess.Popen, data: bytes) -> None:
        """同步写入（在 executor 线程中运行）"""
        process.stdin.write(data)
        process.stdin.flush()

    def _get_timeout(self, method: str) -> float:
        """根据操作类型返回超时值"""
        if method == "initialize":
            return self.config.startup_timeout
        if method == "tools/call":
            return self.config.operation_timeout
        return min(self.config.operation_timeout, 30.0)

    # ── 读取循环 ──

    async def _read_loop(self) -> None:
        """后台协程：从 stdout 读取消息帧"""
        if not self._process or not self._process.stdout:
            return

        stdout = self._process.stdout
        loop = asyncio.get_running_loop()
        _read = lambda n: loop.run_in_executor(None, stdout.read, n)

        while self.state not in (MCPState.DISCONNECTED,):
            try:
                # 1. 逐字节读 header（64KB 上限，空读 100 次判定 EOF）
                header_bytes = b""
                empty_hdr = 0
                while not header_bytes.endswith(b"\r\n\r\n"):
                    ch = await _read(1)
                    if not ch:
                        empty_hdr += 1
                        if empty_hdr > 100 or (self._process and self._process.poll() is not None):
                            break
                        await asyncio.sleep(0.01)
                        continue
                    empty_hdr = 0
                    header_bytes += ch
                    if len(header_bytes) > 65536:
                        logger.warning(f"MCP [{self.config.name}]: header too large")
                        break

                if empty_hdr > 100 or (self._process and self._process.poll() is not None):
                    break

                # 2. 解析 Content-Length（保护异常）
                header = header_bytes.decode("utf-8", errors="replace")
                cl = 0
                for line in header.split("\r\n"):
                    if line.lower().startswith("content-length:"):
                        try:
                            cl = int(line.split(":")[1].strip())
                        except (ValueError, IndexError):
                            logger.warning(f"MCP [{self.config.name}]: bad CL header: {line}")
                if cl <= 0 or cl > self.MAX_MESSAGE_SIZE:
                    continue

                # 3. 读 body（空读 200 次判定 EOF）
                body_bytes = b""
                empty_body = 0
                while len(body_bytes) < cl:
                    need = min(cl - len(body_bytes), 65536)
                    chunk = await _read(need)
                    if not chunk:
                        empty_body += 1
                        if empty_body > 200 or (self._process and self._process.poll() is not None):
                            break
                        await asyncio.sleep(0.01)
                        continue
                    empty_body = 0
                    body_bytes += chunk

                if len(body_bytes) < cl:
                    break

                # 4. 分发
                self._last_activity = time.time()
                try:
                    message = json.loads(body_bytes.decode("utf-8", errors="replace"))
                    self._dispatch_message(message)
                except json.JSONDecodeError:
                    # 尝试 raw_decode（处理尾部多余数据）
                    try:
                        decoder = json.JSONDecoder()
                        message, _ = decoder.raw_decode(body_bytes.decode("utf-8", errors="replace"))
                        self._dispatch_message(message)
                    except json.JSONDecodeError as e:
                        logger.warning(f"MCP [{self.config.name}]: JSON: {e}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"MCP [{self.config.name}]: read err: {e}")
                break

        # 断连
        if self.state == MCPState.READY:
            logger.warning(f"MCP [{self.config.name}]: unexpected disconnect")
            self.state = MCPState.ERROR
            self._cleanup()
            if self.config.auto_reconnect:
                self._start_reconnect()

    def _dispatch_message(self, message: dict) -> None:
        """分发 JSON-RPC 消息"""
        msg_id = message.get("id")
        method = message.get("method")

        if "result" in message:
            if msg_id is not None and msg_id in self._pending:
                self._pending.pop(msg_id).set_result(message["result"])
            elif msg_id is not None:
                logger.debug(f"MCP [{self.config.name}]: stale response id={msg_id}")
            else:
                logger.warning(f"MCP [{self.config.name}]: result without id")

        elif "error" in message:
            err = message["error"]
            err_msg = err.get("message", "unknown")
            err_code = err.get("code", -1)
            readable = _MCP_ERROR_MAP.get(err_code, err_msg)
            exc = MCPProtocolError(f"{readable} (code={err_code}): {err_msg}", self.config.name, err_code)
            if msg_id is not None and msg_id in self._pending:
                self._pending.pop(msg_id).set_exception(exc)
            else:
                logger.warning(f"MCP [{self.config.name}]: server error: {readable}")

        elif method:
            # 服务器通知
            self._handle_server_notification(method, message.get("params", {}))
        else:
            logger.debug(f"MCP [{self.config.name}]: unknown message keys={list(message.keys())}")

    def _handle_server_notification(self, method: str, params: dict) -> None:
        """处理服务器推送的通知"""
        if method == "notifications/tools/list_changed":
            logger.info(f"MCP [{self.config.name}]: tools list changed, refreshing...")
            asyncio.create_task(self.list_tools())
        elif method == "notifications/resources/list_changed":
            logger.debug(f"MCP [{self.config.name}]: resources list changed")
        else:
            logger.debug(f"MCP [{self.config.name}]: notification: {method}")

    # ── 工具接口 ──

    async def list_tools(self) -> list[MCPTool]:
        """获取工具列表（支持动态刷新）"""
        if self.state != MCPState.READY:
            return []

        try:
            result = await self._send_request("tools/list", {})
            tools_data = result.get("tools", [])

            if not isinstance(tools_data, list):
                logger.warning(f"MCP [{self.config.name}]: tools/list returned non-list: {type(tools_data)}")
                return self._tools  # 返回上次缓存

            self._tools = []
            for td in tools_data:
                try:
                    tool = MCPTool(
                        name=td.get("name", "unknown"),
                        description=td.get("description", ""),
                        parameters=td.get("inputSchema", {}),
                        server_name=self.config.name,
                    )
                    self._tools.append(tool)
                except Exception as e:
                    logger.warning(f"MCP [{self.config.name}]: skip bad tool entry: {e}")

            logger.info(f"MCP [{self.config.name}]: {len(self._tools)} tools")
            return list(self._tools)

        except MCPError as e:
            logger.warning(f"MCP [{self.config.name}]: list_tools failed: {e}")
            return list(self._tools)  # 返回缓存
        except Exception as e:
            logger.error(f"MCP [{self.config.name}]: list_tools unexpected error: {e}")
            return list(self._tools)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """调用工具

        Returns:
            文本结果，永远不抛异常
        """
        if self.state != MCPState.READY:
            return f"[MCP] Server '{self.config.name}' is not ready (state={self.state.value})"

        try:
            result = await self._send_request("tools/call", {
                "name": name,
                "arguments": arguments,
            })

            content = result.get("content", result.get("result", []))
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                texts = []
                for item in content:
                    if isinstance(item, dict):
                        t = item.get("type", "text")
                        if t == "text":
                            texts.append(item.get("text", ""))
                        elif t == "image":
                            texts.append("[图片数据]")
                        elif t == "resource":
                            texts.append(f"[资源: {item.get('resource', {}).get('uri', '')}]")
                        else:
                            texts.append(json.dumps(item, ensure_ascii=False))
                return "\n".join(texts) if texts else json.dumps(result, ensure_ascii=False)

            return str(content)

        except MCPTimeoutError:
            return f"[MCP] 工具 '{name}' 执行超时"
        except MCPError as e:
            return f"[MCP] {e}"
        except Exception as e:
            return f"[MCP] 工具 '{name}' 执行失败: {e}"

    # ── 状态 ──

    @property
    def is_connected(self) -> bool:
        return self.state == MCPState.READY

    def get_tools(self) -> list[MCPTool]:
        return list(self._tools)
