"""Stability edge-case tests — MCP 兼容性 + 项目稳定性验证"""

import asyncio
import json
import tempfile
from pathlib import Path

import pytest


# ══════════════════════════════════════════
# MCP Client 边缘测试
# ══════════════════════════════════════════

class TestMCPConfig:
    def test_default_config(self):
        from core.tools.mcp_client import MCPConfig
        cfg = MCPConfig(name="test", command="echo")
        assert cfg.name == "test"
        assert cfg.auto_reconnect is True
        assert cfg.max_reconnect_attempts == 10
        assert cfg.reconnect_backoff == 2.0
        assert cfg.startup_timeout == 30.0

    def test_config_from_dict(self):
        from core.tools.mcp_client import MCPConfig
        data = {"name": "fs", "command": "npx", "args": ["-y", "server"], "max_reconnect_attempts": 3}
        cfg = MCPConfig(**{k: v for k, v in data.items() if k in MCPConfig.__dataclass_fields__})
        assert cfg.max_reconnect_attempts == 3


class TestMCPTool:
    def test_prompt_format(self):
        from core.tools.mcp_client import MCPTool
        tool = MCPTool(
            name="read_file",
            description="Read a file",
            parameters={"properties": {"path": {"description": "File path"}}, "required": ["path"]},
            server_name="fs",
        )
        fmt = tool.to_prompt_format()
        assert "read_file" in fmt
        assert "必填" in fmt
        assert "path" in fmt


class TestMCPErrorHandling:
    def test_connection_error(self):
        from core.tools.mcp_client import MCPConnectionError
        err = MCPConnectionError("test error", "test-srv")
        assert "test-srv" in str(err)
        assert err.code == -1

    def test_timeout_error(self):
        from core.tools.mcp_client import MCPTimeoutError
        err = MCPTimeoutError("timed out", "srv")
        assert "timed out" in str(err)

    def test_protocol_error_with_code(self):
        from core.tools.mcp_client import MCPProtocolError
        err = MCPProtocolError("bad request", "srv", -32600)
        assert err.code == -32600

    def test_state_enum(self):
        from core.tools.mcp_client import MCPState
        assert MCPState.DISCONNECTED.value == "disconnected"
        assert MCPState.READY.value == "ready"


@pytest.mark.asyncio
async def test_mcp_client_command_not_found():
    """不存在的命令 → 连接失败但不崩溃"""
    from core.tools.mcp_client import MCPClient, MCPConfig
    cfg = MCPConfig(name="bad", command="nonexistent_command_xyz_123", startup_timeout=2.0)
    client = MCPClient(cfg)
    result = await client.connect()
    assert result is False
    assert client.state.value == "error"


@pytest.mark.asyncio
async def test_mcp_client_process_exits_immediately():
    """进程立即退出 → 优雅失败"""
    from core.tools.mcp_client import MCPClient, MCPConfig
    cfg = MCPConfig(name="exiter", command="python", args=["-c", "exit(1)"], startup_timeout=3.0)
    client = MCPClient(cfg)
    result = await client.connect()
    assert result is False


@pytest.mark.asyncio
async def test_mcp_client_disconnect_before_connect():
    """未连接时断开 → 不崩溃"""
    from core.tools.mcp_client import MCPClient, MCPConfig
    cfg = MCPConfig(name="dummy", command="python", args=["-c", "import time; time.sleep(10)"], auto_reconnect=False)
    client = MCPClient(cfg)
    await client.disconnect()
    assert client.state.value == "disconnected"


@pytest.mark.asyncio
async def test_mcp_client_call_tool_when_disconnected():
    """未连接时调用工具 → 返回错误消息不崩"""
    from core.tools.mcp_client import MCPClient, MCPConfig
    cfg = MCPConfig(name="dummy", command="python", args=["-c", "import time; time.sleep(10)"], auto_reconnect=False)
    client = MCPClient(cfg)
    result = await client.call_tool("test", {})
    assert "not ready" in result.lower()


class TestMCPManager:
    def test_empty_manager(self):
        from core.tools.mcp_manager import MCPManager
        mgr = MCPManager()
        assert mgr.connected_count == 0
        assert mgr.tools_count == 0
        assert mgr.get_all_tools() == []

    def test_manager_status_empty(self):
        from core.tools.mcp_manager import MCPManager
        mgr = MCPManager()
        status = mgr.get_status()
        assert status == {}

    @pytest.mark.asyncio
    async def test_manager_no_config(self):
        from core.tools.mcp_manager import MCPManager
        mgr = MCPManager()
        connected = await mgr.load_and_connect("/nonexistent/path")
        assert connected == 0

    @pytest.mark.asyncio
    async def test_manager_disconnect_empty(self):
        from core.tools.mcp_manager import MCPManager
        mgr = MCPManager()
        await mgr.disconnect_all()  # 不抛异常


# ══════════════════════════════════════════
# 项目核心稳定性测试
# ══════════════════════════════════════════

class TestPipelineEdgeCases:
    def test_empty_message(self):
        """空消息 → 不崩溃 + 明确返回"""
        from core.chat.pipeline import format_multi_message, get_time_context, get_llm_error_message
        result, count = format_multi_message("")
        assert count == 1
        assert get_time_context()  # 时段字符串不为空
        
        # 错误消息映射
        class FakeError(Exception):
            pass
        msg = get_llm_error_message(FakeError("rate limit 429"))
        assert "太忙" in msg
        msg = get_llm_error_message(FakeError("connection"))
        assert "网络" in msg

    def test_multi_message_formatting(self):
        from core.chat.pipeline import format_multi_message
        result, count = format_multi_message("line1\nline2\nline3")
        assert count == 3
        assert "[消息1]" in result
        assert "[消息3]" in result

    def test_single_message_formatting(self):
        from core.chat.pipeline import format_multi_message
        result, count = format_multi_message("hello")
        assert count == 1
        assert result == "hello"


class TestComponentsIntegration:
    def test_create_components_imports(self):
        from core.app import create_components, AppComponents, ComponentBuilder
        assert callable(create_components)

    def test_config_loading(self):
        from core.config import load_advanced, load_vision_config, load_mcp_config, DEFAULT_PERSONA_ID
        cfg = load_advanced()
        assert "brain_enabled" in cfg
        assert "vision_model" in cfg
        assert isinstance(cfg["vision_model"], dict)

        vision = load_vision_config()
        assert isinstance(vision, dict)

        mcp = load_mcp_config()
        assert isinstance(mcp, list)


class TestChatHandlerStability:
    def test_colors_class(self):
        from core.chat.commands.colors import Colors
        assert Colors.CYAN
        assert Colors.RESET
        assert Colors.DIM

    def test_session_stats(self):
        from core.chat.display import SessionStats
        stats = SessionStats()
        assert stats.message_count == 0
        summary = stats.summary("测试")
        assert "0" in summary
        assert "无变化" in summary

    def test_welcome_message_all_levels(self):
        from core.chat.display import get_welcome_message

        class MockPersona:
            pass
        p = MockPersona()

        for level in [0, 10, 40, 50, 60, 80, 90, 100]:
            msg = get_welcome_message(p, level)
            assert isinstance(msg, str)
            assert len(msg) > 0


class TestToolHandlerStability:
    def test_parse_tool_call_valid(self):
        from core.chat.tool_handler import parse_tool_call
        result = parse_tool_call('【工具调用：weather(city="北京")】')
        assert len(result) == 1
        assert result[0] == ("weather", {"city": "北京"})

    def test_parse_tool_call_multiple_params(self):
        from core.chat.tool_handler import parse_tool_call
        result = parse_tool_call('【工具调用：search(query="天气",limit="5")】')
        assert result[0][1] == {"query": "天气", "limit": "5"}

    def test_parse_tool_call_no_match(self):
        from core.chat.tool_handler import parse_tool_call
        result = parse_tool_call("普通文本没有工具调用")
        assert result == []

    def test_parse_tool_call_multiple_calls(self):
        from core.chat.tool_handler import parse_tool_call
        result = parse_tool_call(
            '【工具调用：weather(city="北京")】和【工具调用：time(format="now")】'
        )
        assert len(result) == 2

    def test_build_tools_prompt_no_tools(self):
        from core.chat.tool_handler import build_tools_prompt
        result = build_tools_prompt(None, None)
        assert result == ""


class TestStorageStability:
    def test_configure_connection(self):
        from core.storage.db import configure_connection, open_db
        import tempfile, sqlite3
        tmp = tempfile.mktemp(suffix=".db")
        try:
            conn = open_db(tmp)
            # 验证 PRAGMA 已设置
            cur = conn.execute("PRAGMA foreign_keys")
            assert cur.fetchone()[0] == 1
            cur = conn.execute("PRAGMA journal_mode")
            assert cur.fetchone()[0] == "wal"
            conn.close()
        finally:
            Path(tmp).unlink(missing_ok=True)

    def test_get_db_context_manager(self):
        from core.storage.db import get_db, get_db_path
        path = get_db_path()
        assert isinstance(path, Path)


# ══════════════════════════════════════════
# 视觉系统测试
# ══════════════════════════════════════════

class TestVisionSystem:
    def test_is_multimodal_detection(self):
        from core.multimodal.vision import is_multimodal_model
        assert is_multimodal_model("gpt-4o") is True
        assert is_multimodal_model("gpt-4-turbo") is True
        assert is_multimodal_model("claude-3-5-sonnet") is True
        assert is_multimodal_model("gemini-1.5-pro") is True
        assert is_multimodal_model("deepseek-v3") is False
        assert is_multimodal_model("gpt-3.5-turbo") is False
        assert is_multimodal_model("") is False
        assert is_multimodal_model(None) is False  # type: ignore

    def test_encode_image(self):
        from core.multimodal.vision import encode_image
        import tempfile, struct, zlib

        # 创建最小合法 PNG
        def create_minimal_png(path):
            # 1x1 红色 PNG
            ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
            ihdr_crc = zlib.crc32(b"IHDR" + ihdr)
            raw = zlib.compress(b"\x00\xff\x00\x00")  # RGBA red
            idat_crc = zlib.crc32(b"IDAT" + raw)
            iend_crc = zlib.crc32(b"IEND")
            with open(path, "wb") as f:
                f.write(b"\x89PNG\r\n\x1a\n")
                f.write(struct.pack(">I", 13) + b"IHDR" + ihdr + struct.pack(">I", ihdr_crc))
                f.write(struct.pack(">I", len(raw)) + b"IDAT" + raw + struct.pack(">I", idat_crc))
                f.write(struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc))

        tmp = tempfile.mktemp(suffix=".png")
        try:
            create_minimal_png(tmp)
            data_url, mime = encode_image(tmp)
            assert data_url.startswith("data:image/png;base64,")
        finally:
            Path(tmp).unlink(missing_ok=True)

    def test_vision_manager_none_model(self):
        from core.multimodal.vision import VisionManager
        vm = VisionManager(main_model=None, vision_config={})
        assert vm.main_is_multimodal is False

    @pytest.mark.asyncio
    async def test_vision_manager_no_config(self):
        from core.multimodal.vision import VisionManager
        vm = VisionManager(main_model=None, vision_config={})
        result = await vm.process("/nonexistent/image.jpg")
        assert "不存在" in result
