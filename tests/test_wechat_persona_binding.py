"""T7: WeChat persona binding — _handle_message 查 ConversationStore 获取 persona_id

验证 _handle_message 闭包（core/app.py run_with_adapters 内定义）正确从
ConversationStore 查询 wechat binding 的 persona_id，而非硬编码 DEFAULT_PERSONA_ID。

测试策略：通过 patch AdapterManager.set_message_handler 捕获 _handle_message 闭包，
mock CLIAdapter.get_input 立即返回 /quit 让 run_with_adapters 退出，
然后直接调用捕获的 handler 验证 persona_id 路由。
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from loguru import logger

from adapters.base import AdapterMessage
from adapters.cli import CLIAdapter
from adapters.debounce import DebounceManager
from adapters.manager import AdapterManager
from core.config import DEFAULT_PERSONA_ID, build_wechat_uid
from core.conversation import ConversationStore


# ────────── 测试辅助 ──────────


class _FakePipeline:
    """捕获 pipeline.process 调用参数"""

    def __init__(self):
        self.calls: list[tuple[str, str, str]] = []

    async def process(self, user_id, content, persona_id, **kwargs):
        self.calls.append((user_id, content, persona_id))
        return ("reply", 0)


class _FakeVisionManager:
    """模拟视觉管理器（非 multimodal 降级路径）"""

    main_is_multimodal = False

    async def process(self, image_path, prompt):
        return "image description"

    def build_enhanced_message(self, vision_result, image_text):
        return f"enhanced: {vision_result} {image_text}"


def _make_app(tmp_path, pipeline, vision_manager=None):
    """构造最小化 AppComponents 供 run_with_adapters 使用"""
    return SimpleNamespace(
        handler=SimpleNamespace(pipeline=pipeline),
        advanced_config={"debounce_seconds": 3},
        conversation_store=ConversationStore(tmp_path / "conversations.json"),
        vision_manager=vision_manager,
        mcp_manager=None,
        persona_loader=SimpleNamespace(
            get=lambda pid: SimpleNamespace(name="小雨")
        ),
        unified_storage=SimpleNamespace(
            get_level=lambda uid, persona_id=None: 0
        ),
        registry=SimpleNamespace(
            get=lambda: SimpleNamespace(model_name="test"),
            available_models=[],
        ),
    )


def _make_wechat_msg(
    account_id="acc1",
    wxid="wxid_test",
    content="hello",
    is_image=False,
    image_path="",
    image_text="",
):
    """构造微信 AdapterMessage"""
    uid = build_wechat_uid(account_id, wxid)
    metadata = {}
    if is_image:
        metadata["is_image"] = True
        metadata["image_path"] = image_path
        metadata["image_text"] = image_text
    return AdapterMessage(
        user_id=uid,
        content=content,
        platform="wechat",
        account_id=account_id,
        metadata=metadata,
    )


@pytest.fixture
async def captured_handler(tmp_path):
    """捕获 _handle_message 闭包 — patches 在测试期间保持激活

    Yields:
        (handler, app, pipeline, debounce_calls)
        - handler: _handle_message 闭包
        - app: SimpleNamespace app 对象（conversation_store 可操作）
        - pipeline: _FakePipeline（捕获 process 调用，用于 image path 测试）
        - debounce_calls: list of (platform, user_id, text, persona_id)
    """
    from core.app import run_with_adapters

    pipeline = _FakePipeline()
    app = _make_app(tmp_path, pipeline)

    handler_holder = {}
    debounce_calls = []

    def capture_handler(self, h):
        handler_holder["h"] = h

    async def fake_get_input(self, timeout=0.5):
        return "/quit"

    async def noop(self):
        pass

    async def fake_add_message(self, platform, user_id, text, persona_id):
        debounce_calls.append((platform, user_id, text, persona_id))

    with (
        patch.object(AdapterManager, "set_message_handler", capture_handler),
        patch.object(CLIAdapter, "get_input", fake_get_input),
        patch.object(AdapterManager, "start_all", noop),
        patch.object(AdapterManager, "stop_all", noop),
        patch.object(DebounceManager, "flush_all", noop),
        patch.object(DebounceManager, "add_message", fake_add_message),
    ):
        await run_with_adapters(app, [])
        yield handler_holder["h"], app, pipeline, debounce_calls


# ────────── 测试用例 ──────────


async def test_wechat_existing_binding_passes_persona_to_debounce(captured_handler):
    """已有 binding persona_id="gf002" → debounce.add_message 收到 "gf002" """
    handler, app, _pipeline, debounce_calls = captured_handler

    app.conversation_store.create(
        "wechat", "acc1", "wxid_test", persona_id="gf002"
    )

    msg = _make_wechat_msg(account_id="acc1", wxid="wxid_test", content="hello")
    await handler(msg)

    assert len(debounce_calls) == 1
    assert debounce_calls[0][3] == "gf002"


async def test_configured_account_persona_overrides_and_syncs_contact_binding(captured_handler):
    """One account role is authoritative for every internal contact binding."""
    handler, app, _pipeline, debounce_calls = captured_handler
    app.advanced_config["adapters"] = {
        "wechat": {"accounts": [{
            "id": "acc1", "enabled": True, "auto_start": True,
            "persona_id": "gf003",
        }]}
    }
    binding = app.conversation_store.create(
        "wechat", "acc1", "wxid_test", persona_id="gf002"
    )

    await handler(_make_wechat_msg(account_id="acc1", wxid="wxid_test"))

    assert debounce_calls[0][3] == "gf003"
    assert app.conversation_store.get(binding.conversation_id).persona_id == "gf003"


async def test_wechat_no_binding_auto_creates_and_uses_default(captured_handler):
    """无 binding → 自动创建 binding + debounce 收到 DEFAULT_PERSONA_ID """
    handler, app, _pipeline, debounce_calls = captured_handler

    msg = _make_wechat_msg(account_id="acc1", wxid="wxid_test", content="hello")
    await handler(msg)

    assert len(debounce_calls) == 1
    assert debounce_calls[0][3] == DEFAULT_PERSONA_ID

    # 验证 binding 已自动创建
    binding = app.conversation_store.find("wechat", "acc1", "wxid_test")
    assert binding is not None
    assert binding.persona_id == DEFAULT_PERSONA_ID


async def test_wechat_rebind_updates_persona_for_next_message(captured_handler):
    """rebind gf002→gf003 后，下一条消息 debounce 收到 "gf003" """
    handler, app, _pipeline, debounce_calls = captured_handler

    binding = app.conversation_store.create(
        "wechat", "acc1", "wxid_test", persona_id="gf002"
    )

    msg = _make_wechat_msg(account_id="acc1", wxid="wxid_test", content="hello")
    await handler(msg)
    assert debounce_calls[0][3] == "gf002"

    # rebind
    app.conversation_store.update_persona(binding.conversation_id, "gf003")

    await handler(msg)
    assert debounce_calls[1][3] == "gf003"


async def test_wechat_image_path_uses_binding_persona(captured_handler):
    """图片消息路径：binding persona_id="gf002" → pipeline.process 收到 "gf002" """
    handler, app, pipeline, debounce_calls = captured_handler

    app.vision_manager = _FakeVisionManager()
    app.conversation_store.create(
        "wechat", "acc1", "wxid_test", persona_id="gf002"
    )

    msg = _make_wechat_msg(
        account_id="acc1",
        wxid="wxid_test",
        content="",
        is_image=True,
        image_path="/tmp/test.png",
        image_text="看看这个",
    )
    await handler(msg)

    # 图片路径直接调 pipeline.process，不走 debounce
    assert len(pipeline.calls) == 1
    assert pipeline.calls[0][2] == "gf002"
    assert len(debounce_calls) == 0


async def test_wechat_store_unreachable_falls_back_to_default(captured_handler):
    """ConversationStore.find 抛异常 → 回退 DEFAULT_PERSONA_ID + 记录 warning """
    from unittest.mock import MagicMock

    handler, app, _pipeline, debounce_calls = captured_handler

    # 用 MagicMock 替换 store，find 抛异常模拟磁盘故障
    mock_store = MagicMock()
    mock_store.find.side_effect = RuntimeError("disk full")
    app.conversation_store = mock_store

    # 捕获 loguru warning（T3 lesson #3: caplog 不接 loguru）
    logs = []
    sink_id = logger.add(logs.append, level="WARNING", format="{message}")
    try:
        msg = _make_wechat_msg(
            account_id="acc1", wxid="wxid_test", content="hello"
        )
        await handler(msg)
    finally:
        logger.remove(sink_id)

    # 不崩溃 + 回退到 DEFAULT_PERSONA_ID
    assert len(debounce_calls) == 1
    assert debounce_calls[0][3] == DEFAULT_PERSONA_ID
    # warning 已记录
    assert any(
        "ConversationStore lookup failed" in log for log in logs
    ), f"Expected warning in logs: {logs}"
