"""Regression tests for asynchronous stability contracts."""

import asyncio
from contextlib import suppress

import pytest

from adapters.debounce import DebounceState
from core.llm.base import BaseLLM
from core.tools.mcp_client import MCPClient, MCPConfig


class StubLLM(BaseLLM):
    def _build_model_id(self) -> str:
        return "provider/test-model"


class FailingStream:
    def __init__(self) -> None:
        self._step = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._step == 0:
            self._step += 1
            delta = type("Delta", (), {"content": "[first_token]"})()
            choice = type("Choice", (), {"delta": delta})()
            return type("Chunk", (), {"choices": [choice]})()
        raise ConnectionError("connection reset after streamed token")


@pytest.mark.asyncio
async def test_stream_does_not_retry_after_first_token(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given
    call_count = 0

    async def fake_acompletion(**_kwargs):
        nonlocal call_count
        call_count += 1
        return FailingStream()

    async def no_delay(_seconds: float) -> None:
        return None

    monkeypatch.setattr("core.llm.base.litellm.acompletion", fake_acompletion)
    monkeypatch.setattr("core.llm.base.asyncio.sleep", no_delay)
    llm = StubLLM(model_name="test-model", api_key="[api_key]", max_retries=1)
    chunks: list[str] = []

    # When
    with pytest.raises(ConnectionError, match="after streamed token"):
        async for chunk in llm.chat_stream([{"role": "user", "content": "[message]"}]):
            chunks.append(chunk)

    # Then
    assert call_count == 1
    assert chunks == ["[first_token]"]


@pytest.mark.asyncio
async def test_reconnect_cleanup_does_not_cancel_current_reconnect_task() -> None:
    # Given
    client = MCPClient(MCPConfig(
        name="[server_name]",
        command="[command]",
        auto_reconnect=False,
    ))

    async def cleanup_from_reconnect_task() -> None:
        client._cleanup()
        await asyncio.sleep(0)

    reconnect_task = asyncio.create_task(cleanup_from_reconnect_task())
    client._reconnect_task = reconnect_task

    # When
    result = await asyncio.gather(reconnect_task, return_exceptions=True)

    # Then
    assert not isinstance(result[0], asyncio.CancelledError)


@pytest.mark.asyncio
async def test_debounce_flush_awaits_segment_delivery() -> None:
    # Given
    send_started = asyncio.Event()
    allow_send = asyncio.Event()
    send_finished = asyncio.Event()

    class Pipeline:
        async def process(self, _user_id: str, _text: str, _persona_id: str):
            return "[reply]", 50

    class Adapter:
        async def send(self, _user_id: str, _content: str) -> bool:
            send_started.set()
            await allow_send.wait()
            send_finished.set()
            return True

    adapter = Adapter()

    class Manager:
        def get(self, _platform: str):
            return adapter

    state = DebounceState(
        platform="[platform]",
        user_id="[user_id]",
        timeout=0,
        pipeline=Pipeline(),
        app=None,
        manager=Manager(),
    )
    state.queue.append("[message]")
    flush_task = asyncio.create_task(state.flush())

    # When
    await asyncio.wait_for(send_started.wait(), timeout=1)
    returned_before_delivery = flush_task.done()
    allow_send.set()
    await asyncio.wait_for(send_finished.wait(), timeout=1)
    with suppress(asyncio.CancelledError):
        await flush_task

    # Then
    assert returned_before_delivery is False


@pytest.mark.asyncio
async def test_debounce_flush_clears_queue_after_processing_failure() -> None:
    # Given
    class Pipeline:
        async def process(self, _user_id: str, _text: str, _persona_id: str):
            raise RuntimeError("[processing_failure]")

    class Manager:
        def get(self, _platform: str):
            return None

    state = DebounceState(
        platform="[platform]",
        user_id="[user_id]",
        timeout=0,
        pipeline=Pipeline(),
        app=None,
        manager=Manager(),
    )
    state.queue.append("[message]")

    # When
    await state.flush()

    # Then
    assert state.queue == []
