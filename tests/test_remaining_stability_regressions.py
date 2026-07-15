"""Regression tests for the remaining v4.1.2 stability gaps."""

import asyncio
import io
import time
from types import SimpleNamespace

import pytest

from core.chat.commands.handler import CommandHandler
from core.chat.handler import ChatHandler
from core.tools.mcp_client import MCPClient, MCPConfig, MCPState
from mcp_servers.framing import FrameReader


class _TimedStdout:
    def read(self, _size: int) -> bytes:
        return b""


class _BlockingStdout:
    def read(self, _size: int) -> bytes:
        time.sleep(0.1)
        return b""


class _RunningProcess:
    stdout = _TimedStdout()

    @staticmethod
    def poll() -> None:
        return None


class _AdvancingClock:
    def __init__(self) -> None:
        self._now = 0.0

    def monotonic(self) -> float:
        self._now += 10.0
        return self._now


class _ChunkStream:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = iter(chunks)

    def read1(self, _size: int) -> bytes:
        return next(self._chunks, b"")


@pytest.mark.asyncio
async def test_read_loop_handles_empty_pipe_read(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given
    client = MCPClient(MCPConfig(name="[server_name]", command="[command]", auto_reconnect=False))
    client._process = _RunningProcess()
    client.state = MCPState.CONNECTING
    # When
    await asyncio.wait_for(client._read_loop(), timeout=0.1)

    # Then
    assert client.state == MCPState.CONNECTING


@pytest.mark.asyncio
async def test_read_loop_times_out_while_pipe_read_is_blocked() -> None:
    # Given
    client = MCPClient(MCPConfig(name="[server_name]", command="[command]", auto_reconnect=False))
    client._process = type("Process", (), {"stdout": _BlockingStdout(), "poll": lambda self: None})()
    client.state = MCPState.CONNECTING
    client.READ_INACTIVITY_TIMEOUT = 0.01

    # When
    await asyncio.wait_for(client._read_loop(), timeout=0.05)

    # Then
    assert client.state == MCPState.CONNECTING


@pytest.mark.asyncio
async def test_command_handler_contains_command_exception(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    # Given
    def fail_command(_handler: CommandHandler) -> None:
        raise RuntimeError("[private_exception_detail]")

    monkeypatch.setattr("core.chat.commands.handler.system_cmds.cmd_help", fail_command)
    handler = CommandHandler(SimpleNamespace())

    # When
    handled = await handler.handle("/help", "[user_id]", "[persona_name]")

    # Then
    assert handled is True
    assert "[private_exception_detail]" not in capsys.readouterr().out


@pytest.mark.asyncio
async def test_chat_handler_persists_partial_reply_before_reraising_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    saved_messages: list[tuple[str, str, str]] = []
    history = SimpleNamespace(add_message=lambda *args: saved_messages.append(args))
    registry = SimpleNamespace(available_models=["[model]"], get=lambda: SimpleNamespace(model_name="[model]"))
    persona_loader = SimpleNamespace(get=lambda _persona_id: SimpleNamespace(name="[persona_name]"))
    proactive = SimpleNamespace(check_proactive_messages=lambda *_args: None)
    handler = ChatHandler(
        registry,
        SimpleNamespace(),
        persona_loader,
        SimpleNamespace(),
        history,
        SimpleNamespace(),
        proactive,
        SimpleNamespace(),
        {"debounce_seconds": 0},
    )

    async def cancel_with_partial(
        _user_id: str,
        _text: str,
        _persona_name: str,
        _stats: object,
        last_reply: list[str],
        **_kwargs: bool,
    ) -> None:
        last_reply[0] = "[partial_reply]"
        raise asyncio.CancelledError

    monkeypatch.setattr(handler, "_process_and_respond", cancel_with_partial)

    original_thread = __import__("threading").Thread

    class InputThread(original_thread):
        def start(self) -> None:
            target = getattr(self, "_target", None)
            if getattr(target, "__name__", "") == "_input_reader":
                target()
                return
            super().start()

    input_values = iter(("[message]", EOFError()))

    def fake_input(_prompt: str) -> str:
        value = next(input_values)
        if isinstance(value, EOFError):
            raise value
        return value

    monkeypatch.setattr("core.chat.handler.threading.Thread", InputThread)
    monkeypatch.setattr("builtins.input", fake_input)

    # When / Then
    with pytest.raises(asyncio.CancelledError):
        await handler.run()
    assert saved_messages == [("local_user", "assistant", "[partial_reply]")]


def test_frame_reader_rejects_header_over_64_kib() -> None:
    # Given
    stream = _ChunkStream([b"X" * (64 * 1024 + 1)])
    reader = FrameReader(stream)

    # When / Then
    with pytest.raises(ValueError, match="header"):
        reader.read()


def test_frame_reader_rejects_body_over_4_mib_before_reading_body() -> None:
    # Given
    header = b"Content-Length: 4194305\r\n\r\n"
    stream = _ChunkStream([header])
    reader = FrameReader(stream)

    # When / Then
    with pytest.raises(ValueError, match="body"):
        reader.read()
