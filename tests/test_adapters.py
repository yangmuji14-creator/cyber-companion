"""AdapterManager 多账号隔离测试 — T3

验证 (platform, account_id) 复合键注册/检索/枚举/隔离，以及向后兼容行为。
"""

import pytest

from adapters.base import BaseAdapter, AdapterConfig, AdapterMessage
from adapters.manager import AdapterManager
from adapters.cli import CLIAdapter
from adapters.wechat import (
    WeChatAdapter,
    _validate_account_id,
    _credential_paths_for,
    _extract_raw_wechat_id,
)


class _TestAdapter(BaseAdapter):
    """轻量测试适配器，模拟 wechat 多账号场景（不依赖 WeChatAdapter）"""

    def __init__(self, platform: str = "wechat"):
        super().__init__(AdapterConfig(platform=platform))
        self.sent: list[tuple[str, str]] = []

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def send(self, user_id: str, content: str, **kwargs) -> bool:
        self.sent.append((user_id, content))
        return True

    async def reply(self, message: AdapterMessage, content: str, **kwargs) -> bool:
        return await self.send(message.user_id, content, **kwargs)


# ── 多账号注册与枚举 ──

def test_multi_account_register_and_list_by_platform():
    """2 个 wechat (acc1/acc2) + 1 cli → list_by_platform 返回 2，get 按 account_id 检索"""
    manager = AdapterManager()
    a1 = _TestAdapter("wechat")
    a2 = _TestAdapter("wechat")
    cli = _TestAdapter("cli")
    manager.register(a1, account_id="acc1")
    manager.register(a2, account_id="acc2")
    manager.register(cli)

    wechats = manager.list_by_platform("wechat")
    assert len(wechats) == 2
    assert manager.get("wechat", "acc1") is a1
    assert manager.get("wechat", "acc2") is a2
    assert manager.get("cli") is cli  # 向后兼容：单账号不传 account_id


def test_register_duplicate_replaces_with_warning():
    """重复 (platform, account_id) → warning + 替换"""
    from loguru import logger as loguru_logger
    manager = AdapterManager()
    a1 = _TestAdapter("wechat")
    a2 = _TestAdapter("wechat")

    captured: list[str] = []
    sink_id = loguru_logger.add(captured.append, level="WARNING", format="{message}")
    try:
        manager.register(a1, account_id="acc1")
        manager.register(a2, account_id="acc1")
    finally:
        loguru_logger.remove(sink_id)

    assert manager.get("wechat", "acc1") is a2
    assert len(manager.list_by_platform("wechat")) == 1
    assert any("replacing" in msg for msg in captured)


def test_list_accounts():
    """list_accounts 返回某平台所有 account_id"""
    manager = AdapterManager()
    manager.register(_TestAdapter("wechat"), account_id="acc1")
    manager.register(_TestAdapter("wechat"), account_id="acc2")
    manager.register(_TestAdapter("cli"))

    accounts = manager.list_accounts("wechat")
    assert set(accounts) == {"acc1", "acc2"}
    assert manager.list_accounts("cli") == ["default"]
    assert manager.list_accounts("nonexistent") == []


def test_list_adapters_returns_all():
    """list_adapters 返回全平台全账号"""
    manager = AdapterManager()
    manager.register(_TestAdapter("wechat"), account_id="acc1")
    manager.register(_TestAdapter("wechat"), account_id="acc2")
    manager.register(_TestAdapter("cli"))
    assert len(manager.list_adapters()) == 3


def test_list_enabled_filters_disabled():
    """list_enabled 过滤 enabled=False"""
    manager = AdapterManager()
    disabled = _TestAdapter("wechat")
    disabled.config.enabled = False
    manager.register(disabled, account_id="acc1")
    manager.register(_TestAdapter("wechat"), account_id="acc2")

    enabled = manager.list_enabled()
    assert len(enabled) == 1
    assert enabled[0].config.account_id == "acc2"


# ── get 向后兼容 ──

def test_get_nonexistent_returns_none():
    """get 不存在的平台/账号 → None"""
    manager = AdapterManager()
    assert manager.get("wechat", "acc1") is None
    assert manager.get("nonexistent") is None


def test_backward_compat_get_single_account_returns_it():
    """单账号场景：get(platform) 不传 account_id → 返回它"""
    manager = AdapterManager()
    a = _TestAdapter("wechat")
    manager.register(a)  # account_id="default"
    assert manager.get("wechat") is a


def test_backward_compat_get_multiple_accounts_raises():
    """多账号场景：get(platform) 不传 account_id → raise ValueError"""
    manager = AdapterManager()
    manager.register(_TestAdapter("wechat"), account_id="acc1")
    manager.register(_TestAdapter("wechat"), account_id="acc2")
    with pytest.raises(ValueError, match="Multiple adapters"):
        manager.get("wechat")


# ── unregister ──

def test_unregister_existing():
    """unregister 已注册的 → True，再 get → None"""
    manager = AdapterManager()
    manager.register(_TestAdapter("wechat"), account_id="acc1")
    assert manager.unregister("wechat", "acc1") is True
    assert manager.get("wechat", "acc1") is None


def test_unregister_nonexistent_returns_false():
    """unregister 不存在的 → False"""
    manager = AdapterManager()
    assert manager.unregister("wechat", "acc1") is False


def test_unregister_default_account_id():
    """unregister 不传 account_id → 注销 default 账号"""
    manager = AdapterManager()
    manager.register(_TestAdapter("wechat"))  # account_id="default"
    assert manager.unregister("wechat") is True
    assert manager.get("wechat") is None


# ── send_to_platform 路由 ──

async def test_send_to_platform_routes_to_correct_account():
    """send_to_platform 按 account_id 路由，不串号"""
    manager = AdapterManager()
    a1 = _TestAdapter("wechat")
    a2 = _TestAdapter("wechat")
    manager.register(a1, account_id="acc1")
    manager.register(a2, account_id="acc2")

    ok = await manager.send_to_platform("wechat", "acc2", "user1", "hello")
    assert ok is True
    assert a2.sent == [("user1", "hello")]
    assert a1.sent == []  # acc1 不应收到


async def test_send_to_platform_nonexistent_returns_false():
    """send_to_platform 不存在的账号 → False"""
    manager = AdapterManager()
    ok = await manager.send_to_platform("wechat", "acc1", "user1", "hello")
    assert ok is False


# ── broadcast ──

async def test_broadcast_reaches_all_enabled():
    """broadcast 默认发到所有 enabled 适配器（所有账号）"""
    manager = AdapterManager()
    a1 = _TestAdapter("wechat")
    a2 = _TestAdapter("wechat")
    cli = _TestAdapter("cli")
    manager.register(a1, account_id="acc1")
    manager.register(a2, account_id="acc2")
    manager.register(cli)

    results = await manager.broadcast("ping")
    assert results == {"wechat:acc1": True, "wechat:acc2": True, "cli:default": True}
    assert a1.sent == [("", "ping")]
    assert a2.sent == [("", "ping")]
    assert cli.sent == [("", "ping")]


async def test_broadcast_filtered_by_platform():
    """broadcast platforms 参数限定平台（仍覆盖该平台所有账号）"""
    manager = AdapterManager()
    a1 = _TestAdapter("wechat")
    cli = _TestAdapter("cli")
    manager.register(a1, account_id="acc1")
    manager.register(cli)

    results = await manager.broadcast("ping", platforms=["wechat"])
    assert results == {"wechat:acc1": True}
    assert a1.sent == [("", "ping")]
    assert cli.sent == []


async def test_broadcast_skips_disabled():
    """broadcast 跳过 disabled 适配器"""
    manager = AdapterManager()
    disabled = _TestAdapter("wechat")
    disabled.config.enabled = False
    manager.register(disabled, account_id="acc1")
    results = await manager.broadcast("ping")
    assert results == {}


# ── AdapterConfig / BaseAdapter account_id ──

def test_adapter_config_default_account_id():
    """AdapterConfig 默认 account_id="default" """
    config = AdapterConfig(platform="cli")
    assert config.account_id == "default"


def test_base_adapter_account_id_property():
    """BaseAdapter.account_id 读自 config"""
    adapter = _TestAdapter("wechat")
    assert adapter.account_id == "default"
    adapter.config.account_id = "acc1"
    assert adapter.account_id == "acc1"


def test_register_syncs_account_id_into_config():
    """register 将 account_id 同步到 adapter.config，保证 adapter.account_id 一致"""
    manager = AdapterManager()
    a = _TestAdapter("wechat")
    manager.register(a, account_id="acc1")
    assert a.account_id == "acc1"
    assert a.config.account_id == "acc1"


# ── CLIAdapter 向后兼容 ──

def test_cli_adapter_default_account_id():
    """CLIAdapter() 无参 → account_id="default" """
    cli = CLIAdapter()
    assert cli.account_id == "default"
    assert cli.config.platform == "cli"


def test_cli_adapter_custom_account_id():
    """CLIAdapter(account_id=...) → 存入 config"""
    cli = CLIAdapter(account_id="acc1")
    assert cli.account_id == "acc1"


def test_cli_adapter_register_and_get_backward_compat():
    """模拟 test_integration_connectivity 的用法：register(cli) + get('cli')"""
    manager = AdapterManager()
    cli = CLIAdapter()
    manager.register(cli)
    assert manager.get("cli") is not None
    assert manager.get("cli") is cli


# ── 并发安全（threading.Lock）──

def test_concurrent_register_is_safe():
    """并发 register 不丢适配器（threading.Lock 保护）"""
    import threading
    manager = AdapterManager()
    n = 20
    adapters = [_TestAdapter("wechat") for _ in range(n)]
    accounts = [f"acc{i}" for i in range(n)]

    def register_one(adapter, account_id):
        manager.register(adapter, account_id=account_id)

    threads = [
        threading.Thread(target=register_one, args=(adapters[i], accounts[i]))
        for i in range(n)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(manager.list_by_platform("wechat")) == n
    for i in range(n):
        assert manager.get("wechat", f"acc{i}") is adapters[i]


# ── T4: WeChatAdapter 多账号凭证路径 / user_id 隔离 ──


def test_wechat_adapter_default_account_id_backward_compat():
    """WeChatAdapter() 无参 → account_id="default"，凭证路径用旧 wechat.json（向后兼容）"""
    a = WeChatAdapter()
    assert a.account_id == "default"
    assert a._credentials_file.name == "wechat.json"
    assert a._sync_file.name == "wechat.json.sync"


def test_wechat_adapter_custom_account_id_uses_namespaced_paths():
    """WeChatAdapter(account_id="acc1") → 凭证路径 wechat_acc1.json / wechat_acc1.json.sync"""
    a = WeChatAdapter(account_id="acc1")
    assert a.account_id == "acc1"
    assert a._credentials_file.name == "wechat_acc1.json"
    assert a._sync_file.name == "wechat_acc1.json.sync"


def test_wechat_adapter_two_accounts_have_isolated_credential_paths():
    """2 个 WeChatAdapter(acc1, acc2) → 凭证路径与 sync 文件全部不同"""
    a1 = WeChatAdapter(account_id="acc1")
    a2 = WeChatAdapter(account_id="acc2")
    assert a1._credentials_file != a2._credentials_file
    assert a1._sync_file != a2._sync_file
    assert a1._credentials_file.name == "wechat_acc1.json"
    assert a2._credentials_file.name == "wechat_acc2.json"


def test_wechat_adapter_account_id_synced_to_config():
    """WeChatAdapter(account_id="acc1") → config.account_id == "acc1"（T3 register 同步前置条件）"""
    a = WeChatAdapter(account_id="acc1")
    assert a.config.account_id == "acc1"
    assert a.account_id == a.config.account_id


# ── account_id 校验：path traversal / 长度 / 字符集 ──


@pytest.mark.parametrize("bad_id", [
    "../etc",      # path traversal
    "..",
    "a/b",         # slash
    "a\\b",        # backslash
    "a..b",        # double dot substring
    "a:b",         # colon (would conflict with user_id :: separator)
    "a b",         # space
    "a.b",         # dot
    "a@b",         # special char
    "ab",          # too short (len 2 < 3)
    "a" * 33,      # too long (len 33 > 32)
    "",            # empty
])
def test_wechat_adapter_rejects_invalid_account_id(bad_id):
    """非法 account_id 一律 raise ValueError（防 path traversal + 长度 + 字符集）"""
    with pytest.raises(ValueError):
        WeChatAdapter(account_id=bad_id)


@pytest.mark.parametrize("ok_id", [
    "default",     # 豁免长度限制
    "abc",         # 最小长度 3
    "a" * 32,      # 最大长度 32
    "a-b_c",       # 连字符 + 下划线
    "Account1",    # 混合大小写
    "acc-123_xyz",
])
def test_wechat_adapter_accepts_valid_account_id(ok_id):
    """合法 account_id 接受"""
    a = WeChatAdapter(account_id=ok_id)
    assert a.account_id == ok_id


def test_validate_account_id_default_exempt_from_length():
    """default 豁免长度限制（虽然 len('default')==7 在 3-32 内，但语义上单独豁免）"""
    assert _validate_account_id("default") == "default"


# ── user_id 复合格式 wechat::{account_id}::{from_user} ──


class _FakeWeChatMsg:
    """模拟 weixin-ilink 消息对象（测试专用，wxid 用占位符）"""

    def __init__(self, from_user: str = "wxid_test", text: str = "hello",
                 message_id: str = "msg_001", context_token: str = ""):
        self.from_user = from_user
        self.text = text
        self.message_id = message_id
        self.context_token = context_token

    def reply_typing(self):
        pass

    def reply_text(self, _text):
        pass


async def _drive_on_inbound_message(adapter: WeChatAdapter, msg):
    """驱动 _on_inbound_message，捕获传给 handler 的 AdapterMessage.user_id

    handler 返回空串 → 触发 msg.reply_text("收到啦~") 但不进入 _send_segmented。
    """
    captured: list[str] = []

    async def _capture(message: AdapterMessage) -> str:
        captured.append(message.user_id)
        return ""  # 空回复，跳过 _send_segmented

    adapter.set_handler(_capture)
    await adapter._on_inbound_message(msg)
    return captured


async def test_wechat_user_id_format_includes_account_id():
    """模拟 inbound msg → user_id = wechat::{account_id}::{from_user}"""
    a1 = WeChatAdapter(account_id="acc1")
    msg = _FakeWeChatMsg(from_user="wxid_test")
    captured = await _drive_on_inbound_message(a1, msg)
    assert captured == ["wechat::acc1::wxid_test"]


async def test_wechat_user_id_isolated_across_accounts():
    """同一 wxid 在 acc1 / acc2 上 → user_id 不同（账号隔离核心保证）"""
    a1 = WeChatAdapter(account_id="acc1")
    a2 = WeChatAdapter(account_id="acc2")
    msg = _FakeWeChatMsg(from_user="wxid_test")

    cap1 = await _drive_on_inbound_message(a1, msg)
    cap2 = await _drive_on_inbound_message(a2, msg)
    assert cap1 == ["wechat::acc1::wxid_test"]
    assert cap2 == ["wechat::acc2::wxid_test"]
    assert cap1[0] != cap2[0]


async def test_wechat_user_id_default_account_format():
    """default 账号 → user_id = wechat::default::{from_user}"""
    a = WeChatAdapter()
    msg = _FakeWeChatMsg(from_user="wxid_test")
    captured = await _drive_on_inbound_message(a, msg)
    assert captured == ["wechat::default::wxid_test"]


# ── _extract_raw_wechat_id: send/send_typing 反向解析 ──


def test_extract_raw_wechat_id_new_format():
    """新格式 wechat::acc1::wxid_test → wxid_test"""
    assert _extract_raw_wechat_id("wechat::acc1::wxid_test") == "wxid_test"
    assert _extract_raw_wechat_id("wechat::default::wxid_test") == "wxid_test"
    assert _extract_raw_wechat_id("wechat::acc-1::wxid_test") == "wxid_test"


def test_extract_raw_wechat_id_legacy_format():
    """旧格式 wechat_wxid_legacy → wxid_legacy（向后兼容历史 user_id）"""
    assert _extract_raw_wechat_id("wechat_wxid_legacy") == "wxid_legacy"
    assert _extract_raw_wechat_id("wechat_wxid_test") == "wxid_test"


def test_extract_raw_wechat_id_passthrough():
    """非 wechat 前缀 → 原样返回（防御性）"""
    assert _extract_raw_wechat_id("raw_id_only") == "raw_id_only"


def test_extract_raw_wechat_id_preserves_colons_in_from_user():
    """from_user 本身含 :: 时，split('::', 2) 保留后续部分"""
    # wechat :: acc1 :: wxid::with::colons
    uid = "wechat::acc1::wxid::with::colons"
    assert _extract_raw_wechat_id(uid) == "wxid::with::colons"


# ── _build_wechat_adapters: settings.json → WeChatAdapter 列表 ──


def test_build_wechat_adapters_new_array_format():
    """新格式 accounts 数组 → 每个 enabled 账号一个 WeChatAdapter"""
    from core.app import _build_wechat_adapters
    cfg = {
        "adapters": {
            "wechat": {
                "accounts": [
                    {"id": "acc1", "enabled": True, "auto_start": True},
                    {"id": "acc2", "enabled": True, "auto_start": True},
                    {"id": "acc3", "enabled": False, "auto_start": True},
                ]
            }
        }
    }
    adapters = _build_wechat_adapters(cfg)
    assert len(adapters) == 2  # acc3 disabled, skipped
    assert {a.account_id for a in adapters} == {"acc1", "acc2"}
    # 凭证路径隔离
    cred_files = {a._credentials_file.name for a in adapters}
    assert cred_files == {"wechat_acc1.json", "wechat_acc2.json"}


def test_build_wechat_adapters_old_single_object_migrates_to_default():
    """旧格式 {enabled, auto_start} → 迁移为单个 default 账号"""
    from core.app import _build_wechat_adapters
    cfg = {
        "adapters": {
            "wechat": {"enabled": True, "auto_start": True}
        }
    }
    adapters = _build_wechat_adapters(cfg)
    assert len(adapters) == 1
    assert adapters[0].account_id == "default"
    assert adapters[0]._credentials_file.name == "wechat.json"  # 旧路径


def test_build_wechat_adapters_no_config_returns_default():
    """adapters 配置缺失 → 返回单个 default 账号（向后兼容最旧调用）"""
    from core.app import _build_wechat_adapters
    adapters = _build_wechat_adapters({})
    assert len(adapters) == 1
    assert adapters[0].account_id == "default"


def test_build_wechat_adapters_skips_disabled():
    """enabled=False 的账号跳过"""
    from core.app import _build_wechat_adapters
    cfg = {
        "adapters": {
            "wechat": {
                "accounts": [
                    {"id": "acc1", "enabled": False},
                    {"id": "acc2", "enabled": True},
                ]
            }
        }
    }
    adapters = _build_wechat_adapters(cfg)
    assert len(adapters) == 1
    assert adapters[0].account_id == "acc2"


def test_build_wechat_adapters_default_id_when_missing():
    """accounts 项缺 id 字段 → 兜底 default"""
    from core.app import _build_wechat_adapters
    cfg = {
        "adapters": {
            "wechat": {
                "accounts": [
                    {"enabled": True},
                ]
            }
        }
    }
    adapters = _build_wechat_adapters(cfg)
    assert len(adapters) == 1
    assert adapters[0].account_id == "default"


# ── register 流程：account_id → AdapterManager 多账号键 ──


def test_wechat_adapter_register_two_accounts_in_manager():
    """2 个 WeChatAdapter 通过 manager.register 注册 → (wechat, acc1) / (wechat, acc2) 键隔离"""
    manager = AdapterManager()
    a1 = WeChatAdapter(account_id="acc1")
    a2 = WeChatAdapter(account_id="acc2")
    manager.register(a1, account_id="acc1")
    manager.register(a2, account_id="acc2")

    assert manager.get("wechat", "acc1") is a1
    assert manager.get("wechat", "acc2") is a2
    assert manager.get("wechat", "acc1") is not a2
    assert len(manager.list_by_platform("wechat")) == 2
