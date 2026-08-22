import json
from types import SimpleNamespace

import pytest

from core.chat.pipeline import ChatPipeline
from core.chat.context_builder import trim_messages_to_budget
from core.chat.tool_handler import call_llm_with_tools, parse_tool_call
from core.llm.base import BaseLLM, LLMResponse
from core.memory.manager import MemoryManager
from core.memory.models import Memory
from core.runtime import BackgroundTaskManager
from core.runtime import RuntimeMetrics
from core.storage.backup import (
    apply_pending_restore,
    create_backup,
    pending_restore_status,
    restore_backup,
    schedule_restore,
)
from core.tools.base import BaseTool, ToolRegistry, ToolResult


class StubLLM(BaseLLM):
    def _build_model_id(self) -> str:
        return "provider/test-model"


def test_legacy_slash_tool_call_remains_supported():
    assert parse_tool_call('稍等，我来查 /call clock') == [("clock", {})]


def test_memory_similarity_threshold_filters_noise_but_keeps_keyword_overlap():
    manager = MemoryManager.__new__(MemoryManager)
    candidates = [
        Memory(id="noise", content="unrelated trip", level=5),
        Memory(id="semantic", content="jazz recommendations", level=3),
        Memory(id="keyword", content="music archive", level=2),
    ]

    prompt = manager._hybrid_rank_prompt(
        candidates,
        cand_vecs=[[0.1, 0.99], [0.8, 0.6], [0.1, 0.99]],
        query_vec=[1.0, 0.0],
        limit=8,
        query="favorite music",
    )

    assert "unrelated trip" not in prompt
    assert "jazz recommendations" in prompt
    assert "music archive" in prompt


def test_context_budget_keeps_current_request_and_complete_recent_turns():
    messages = [
        {"role": "user", "content": "old-user-" + "x" * 80},
        {"role": "assistant", "content": "old-assistant-" + "x" * 80},
        {"role": "user", "content": "recent-user"},
        {"role": "assistant", "content": "recent-assistant"},
        {"role": "system", "content": "dynamic-context"},
        {"role": "user", "content": "current-user"},
    ]

    trimmed = trim_messages_to_budget(
        messages, max_chars=100, reserved_chars=20,
    )

    assert trimmed == messages[2:]
    assert messages[0]["content"].startswith("old-user-")


def test_context_budget_never_drops_current_user_when_message_exceeds_budget():
    current = {"role": "user", "content": "x" * 500}
    assert trim_messages_to_budget([current], max_chars=100) == [current]


def test_runtime_metrics_aggregate_without_request_content():
    metrics = RuntimeMetrics()
    metrics.record(
        "pipeline.reply", 120.5,
        usage={"prompt_tokens": 10, "completion_tokens": 4},
    )
    metrics.record("pipeline.reply", 80, success=False)

    snapshot = metrics.snapshot()
    reply = snapshot["operations"]["pipeline.reply"]
    assert reply == {
        "count": 2,
        "failures": 1,
        "avg_ms": 100.2,
        "max_ms": 120.5,
        "prompt_tokens": 10,
        "completion_tokens": 4,
        "total_tokens": 14,
    }
    assert "content" not in json.dumps(snapshot)


@pytest.mark.asyncio
async def test_pipeline_shutdown_cancels_background_work():
    pipeline = ChatPipeline.__new__(ChatPipeline)
    pipeline._tasks = BackgroundTaskManager()
    started = __import__("asyncio").Event()

    async def work():
        started.set()
        await __import__("asyncio").Event().wait()

    pipeline._run_background(work())
    await started.wait()
    await pipeline.shutdown()
    assert pipeline._tasks.active_count == 0


@pytest.mark.asyncio
async def test_llm_response_exposes_native_tool_calls(monkeypatch):
    response = SimpleNamespace(
        choices=[SimpleNamespace(
            message=SimpleNamespace(
                content=None,
                tool_calls=[SimpleNamespace(
                    id="call_weather",
                    type="function",
                    function=SimpleNamespace(
                        name="weather",
                        arguments='{"city":"北京","days":2}',
                    ),
                )],
            ),
            finish_reason="tool_calls",
        )],
        usage=None,
    )

    async def fake_acompletion(**_kwargs):
        return response

    monkeypatch.setattr("core.llm.base.litellm.acompletion", fake_acompletion)
    result = await StubLLM("test-model", "test-key").chat(
        [{"role": "user", "content": "天气"}],
        tools=[{"type": "function", "function": {"name": "weather"}}],
    )

    assert result.content == ""
    assert result.metadata["tool_calls"] == [{
        "id": "call_weather",
        "type": "function",
        "name": "weather",
        "arguments": {"city": "北京", "days": 2},
    }]


@pytest.mark.asyncio
async def test_stream_reconstructs_fragmented_native_tool_call(monkeypatch):
    class Stream:
        def __init__(self, chunks):
            self._chunks = chunks

        def __aiter__(self):
            self._iterator = iter(self._chunks)
            return self

        async def __anext__(self):
            try:
                return next(self._iterator)
            except StopIteration as e:
                raise StopAsyncIteration from e

    def chunk(tool_call):
        return SimpleNamespace(choices=[SimpleNamespace(
            delta=SimpleNamespace(content=None, tool_calls=[tool_call]),
        )])

    chunks = [
        chunk(SimpleNamespace(
            index=0, id="call_",
            function=SimpleNamespace(name="wea", arguments='{"city":"'),
        )),
        chunk(SimpleNamespace(
            index=0, id="1",
            function=SimpleNamespace(name="ther", arguments='北京"}'),
        )),
    ]

    async def fake_acompletion(**_kwargs):
        return Stream(chunks)

    monkeypatch.setattr("core.llm.base.litellm.acompletion", fake_acompletion)
    events = [event async for event in StubLLM("test-model", "test-key").chat_stream_events(
        [{"role": "user", "content": "天气"}], tools=[]
    )]

    assert len(events) == 1
    assert events[0].tool_call == {
        "id": "call_1",
        "type": "function",
        "name": "weather",
        "arguments": {"city": "北京"},
    }


@pytest.mark.asyncio
async def test_native_tool_call_executes_and_uses_tool_role():
    class EchoTool(BaseTool):
        name = "echo"
        description = "Echo text"

        @property
        def parameters(self):
            return {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            }

        async def execute(self, **kwargs):
            return ToolResult(success=True, output=kwargs["text"])

    registry = ToolRegistry()
    registry.register(EchoTool())

    class Pipeline:
        _tool_registry = registry

        def __init__(self):
            self.follow_up = None

        async def _llm_call_response(self, _messages, _system, **kwargs):
            assert kwargs["tools"][0]["function"]["name"] == "echo"
            return LLMResponse(
                content="",
                model="test",
                metadata={"tool_calls": [{
                    "id": "call_echo",
                    "type": "function",
                    "name": "echo",
                    "arguments": {"text": "hello"},
                }]},
            )

        async def _llm_call(self, messages, _system, on_token=None):
            self.follow_up = messages
            if on_token:
                on_token("done")
            return "done"

    pipeline = Pipeline()
    tokens = []
    reply = await call_llm_with_tools(
        pipeline,
        [{"role": "user", "content": "echo"}],
        "system",
        tokens.append,
    )

    assert reply == "done"
    assert tokens == ["done"]
    assert pipeline.follow_up[-1]["role"] == "tool"
    assert pipeline.follow_up[-1]["tool_call_id"] == "call_echo"
    assert "hello" in pipeline.follow_up[-1]["content"]


def test_scheduled_restore_is_applied_only_on_next_start(tmp_path):
    data_dir = tmp_path / "data"
    config_dir = tmp_path / "config"
    data_dir.mkdir()
    config_dir.mkdir()
    conversation = data_dir / "conversations.json"
    conversation.write_text('{"state":"backup"}', encoding="utf-8")
    archive = create_backup(data_dir, config_dir)
    conversation.write_text('{"state":"current"}', encoding="utf-8")

    queued = schedule_restore(archive, data_dir)
    assert queued["pending"] is True
    assert "current" in conversation.read_text(encoding="utf-8")
    assert pending_restore_status(data_dir) is not None

    result = apply_pending_restore(data_dir, config_dir)
    assert result is not None
    assert "backup" in conversation.read_text(encoding="utf-8")
    assert pending_restore_status(data_dir) is None
    assert result["safety_backup"]


def test_legacy_backup_restore_clears_consolidated_store_for_next_migration(tmp_path):
    import sqlite3
    import zipfile

    data_dir = tmp_path / "data"
    config_dir = tmp_path / "config"
    data_dir.mkdir()
    config_dir.mkdir()
    current = data_dir / "companion.db"
    conn = sqlite3.connect(current)
    conn.execute("CREATE TABLE current_data (value TEXT)")
    conn.execute("INSERT INTO current_data VALUES ('current')")
    conn.commit()
    conn.close()

    legacy = tmp_path / "legacy.zip"
    manifest = {"format_version": 1, "included": ["data/memories.db"]}
    with zipfile.ZipFile(legacy, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        snapshot = sqlite3.connect(":memory:")
        snapshot.execute("CREATE TABLE memories (user_id TEXT, id TEXT, content TEXT)")
        snapshot.execute("INSERT INTO memories VALUES ('u', 'm', 'old')")
        snapshot.commit()
        # Use a temporary on-disk SQLite file so the archive contains a valid DB.
        old_db = data_dir / "memories.db"
        target = sqlite3.connect(old_db)
        snapshot.backup(target)
        target.close()
        snapshot.close()
        archive.write(old_db, "data/memories.db")
        old_db.unlink()

    result = restore_backup(legacy, data_dir, config_dir)
    assert result["restored"] == ["data/memories.db"]
    assert not current.exists()
    assert (data_dir / "memories.db").exists()
