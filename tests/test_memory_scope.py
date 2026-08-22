"""Regression tests for persona/bound-conversation memory isolation."""

from types import SimpleNamespace

import pytest

from adapters.debounce import DebounceManager
from core.chat.commands import tool_cmds
from core.chat.commands.handler import CommandHandler
from core.config import build_memory_scope_uid
from core.memory.chat_history import ChatHistoryStorage
from core.memory.manager import MemoryManager


def test_memory_scope_is_stable_but_changes_with_binding():
    first = build_memory_scope_uid("wechat::acc1::wxid", "role_a", "conv_1")
    assert first == build_memory_scope_uid("wechat::acc1::wxid", "role_a", "conv_1")
    assert first != build_memory_scope_uid("wechat::acc1::wxid", "role_b", "conv_1")
    assert first != build_memory_scope_uid("wechat::acc1::wxid", "role_a", "conv_2")
    assert first.startswith("scope_")
    assert "/" not in first and "\\" not in first


def test_chat_history_isolated_between_persona_scopes(tmp_path):
    storage = ChatHistoryStorage(tmp_path, max_messages=20)
    role_a = build_memory_scope_uid("wechat::acc1::wxid", "role_a", "conv_1")
    role_b = build_memory_scope_uid("wechat::acc1::wxid", "role_b", "conv_1")

    storage.add_message(role_a, "user", "只给角色 A 的信息")
    storage.add_message(role_b, "user", "只给角色 B 的信息")

    assert [m["content"] for m in storage.get_messages(role_a)] == ["只给角色 A 的信息"]
    assert [m["content"] for m in storage.get_messages(role_b)] == ["只给角色 B 的信息"]
    assert storage._get_user_file(role_a) != storage._get_user_file(role_b)


def test_long_term_memory_isolated_between_persona_scopes(tmp_path):
    manager = MemoryManager(tmp_path)
    role_a = build_memory_scope_uid("wechat::acc1::wxid", "role_a", "conv_1")
    role_b = build_memory_scope_uid("wechat::acc1::wxid", "role_b", "conv_1")

    manager.add_memory_sync(role_a, "用户只告诉角色 A 的秘密", level=5)

    assert [m.content for m in manager.get_memories(role_a)] == ["用户只告诉角色 A 的秘密"]
    assert manager.get_memories(role_b) == []


class _Pipeline:
    def __init__(self):
        self.calls = []

    async def process(self, user_id, content, persona_id, scope_id=None):
        self.calls.append((user_id, content, persona_id, scope_id))
        return "ok", 50


class _Adapter:
    async def send(self, _user_id, _text):
        return None


class _AdapterManager:
    def get(self, _platform):
        return _Adapter()


@pytest.mark.asyncio
async def test_debounce_uses_scope_as_queue_boundary():
    pipeline = _Pipeline()
    manager = DebounceManager(60, pipeline, object(), _AdapterManager())
    base = "wechat::acc1::wxid"
    role_a = build_memory_scope_uid(base, "role_a", "conv_1")
    role_b = build_memory_scope_uid(base, "role_b", "conv_1")

    await manager.add_message("wechat", base, "给 A", persona_id="role_a", scope_id=role_a)
    await manager.add_message("wechat", base, "给 B", persona_id="role_b", scope_id=role_b)
    await manager.flush_all()

    assert {(call[1], call[2], call[3]) for call in pipeline.calls} == {
        ("给 A", "role_a", role_a),
        ("给 B", "role_b", role_b),
    }


@pytest.mark.asyncio
async def test_cli_regen_reads_and_replies_inside_persona_scope():
    external_user = "local_user"
    persona_id = "role_a"
    scope_id = build_memory_scope_uid(external_user, persona_id, "cli")
    history_calls = []
    pipeline_calls = []

    class _History:
        def get_messages(self, user_id):
            history_calls.append(("get", user_id))
            return [
                {"role": "user", "content": "原问题"},
                {"role": "assistant", "content": "旧回复"},
            ]

        def delete_last_messages(self, user_id, count):
            history_calls.append(("delete", user_id, count))
            return [{"role": "assistant", "content": "旧回复"}]

    async def _process(*args, **kwargs):
        pipeline_calls.append((args, kwargs))
        return "新回复", 50

    chat_handler = SimpleNamespace(
        current_persona_id=persona_id,
        get_memory_scope_id=lambda user_id, selected=None: build_memory_scope_uid(
            user_id, selected or persona_id, "cli",
        ),
        _scope_kwargs=lambda user_id: {"scope_id": scope_id},
        chat_history=_History(),
        pipeline=SimpleNamespace(process=_process),
        persona_loader=SimpleNamespace(get=lambda _id: SimpleNamespace(name="角色 A")),
    )
    commands = CommandHandler(chat_handler)

    await tool_cmds.cmd_regen(commands, external_user, "角色 A")

    assert history_calls == [
        ("get", scope_id),
        ("delete", scope_id, 1),
    ]
    assert pipeline_calls[0][0][:3] == (external_user, "原问题", persona_id)
    assert pipeline_calls[0][1] == {"skip_user_message": True, "scope_id": scope_id}
