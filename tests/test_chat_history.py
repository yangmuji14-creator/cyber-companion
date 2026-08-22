"""T5: 复合 user_id 方案 + 子目录存储 + parse_uid 测试

覆盖：
- build_wechat_uid / build_web_uid / build_cli_uid / build_api_uid 构造
- parse_uid 4 平台 round-trip + malformed 不抛异常
- ChatHistoryStorage._get_user_file 子目录结构（wechat/web/cli/api）
- _get_user_file legacy 路径（无 :: 的旧 user_id）
- _get_user_file 路径穿越防护（ValueError）
- add_message 携带 platform/persona_id/account_id 字段 round-trip
- add_message 不传新字段（向后兼容旧调用）
- 子目录在 Windows 可创建（测试自动跑在 Windows 上即验证）
"""

import sys
import tempfile
from pathlib import Path

import pytest

_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))

from core.config import (
    SEP,
    USER_ID_SCHEME,
    build_api_uid,
    build_cli_uid,
    build_web_uid,
    build_wechat_uid,
    parse_uid,
)
from core.memory.chat_history import ChatHistoryStorage


# ─────────────────────────────────────────────────────────────
# build_*_uid 构造测试
# ─────────────────────────────────────────────────────────────


class TestBuildUid:
    def test_build_wechat_uid_format(self):
        assert build_wechat_uid("acc1", "wxid_abc") == f"wechat{SEP}acc1{SEP}wxid_abc"

    def test_build_web_uid_format(self):
        assert build_web_uid("gf001") == f"web{SEP}gf001"

    def test_build_cli_uid_format(self):
        assert build_cli_uid() == f"cli{SEP}local"

    def test_build_api_uid_format(self):
        assert build_api_uid("user1") == f"api{SEP}user1"

    def test_user_id_scheme_constant(self):
        assert USER_ID_SCHEME == "v2"

    def test_sep_is_double_colon(self):
        assert SEP == "::"


# ─────────────────────────────────────────────────────────────
# parse_uid 解析测试
# ─────────────────────────────────────────────────────────────


class TestParseUid:
    def test_parse_wechat_round_trip(self):
        uid = build_wechat_uid("acc1", "wxid_abc")
        parsed = parse_uid(uid)
        assert parsed == {
            "platform": "wechat",
            "account_id": "acc1",
            "persona_id": "",
            "raw_id": "wxid_abc",
        }

    def test_parse_web_round_trip(self):
        uid = build_web_uid("gf001")
        parsed = parse_uid(uid)
        assert parsed == {
            "platform": "web",
            "account_id": "",
            "persona_id": "gf001",
            "raw_id": "gf001",
        }

    def test_parse_cli_round_trip(self):
        uid = build_cli_uid()
        parsed = parse_uid(uid)
        assert parsed == {
            "platform": "cli",
            "account_id": "",
            "persona_id": "",
            "raw_id": "local",
        }

    def test_parse_api_round_trip(self):
        uid = build_api_uid("user1")
        parsed = parse_uid(uid)
        assert parsed == {
            "platform": "api",
            "account_id": "",
            "persona_id": "",
            "raw_id": "user1",
        }

    def test_parse_malformed_no_colons_returns_unknown(self):
        parsed = parse_uid("malformed_no_colons")
        assert parsed["platform"] == "unknown"
        assert parsed["account_id"] == ""
        assert parsed["persona_id"] == ""
        assert parsed["raw_id"] == "malformed_no_colons"

    def test_parse_empty_string_returns_unknown(self):
        parsed = parse_uid("")
        assert parsed["platform"] == "unknown"
        assert parsed["raw_id"] == ""

    def test_parse_legacy_wechat_underscore_format_returns_unknown(self):
        """旧 WeChatAdapter 用 `wechat_<wxid>` 下划线格式，parse_uid 应返回 unknown。"""
        parsed = parse_uid("wechat_wxid_abc")
        assert parsed["platform"] == "unknown"
        assert parsed["raw_id"] == "wechat_wxid_abc"

    def test_parse_single_colon_format_returns_unknown(self):
        """单冒号分隔（如 `wechat:acc1:wxid`）不匹配双冒号方案，返回 unknown。"""
        parsed = parse_uid("wechat:acc1:wxid_abc")
        assert parsed["platform"] == "unknown"

    def test_parse_never_raises(self):
        """parse_uid 对任何输入都不应抛异常。"""
        for uid in ["", "a", "::", "::::", "wechat::", "::wxid", "web::", "unknown::x::y::z"]:
            # 不抛即通过
            parse_uid(uid)


# ─────────────────────────────────────────────────────────────
# _get_user_file 子目录结构测试
# ─────────────────────────────────────────────────────────────


class TestGetUserFileSubdirectories:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp(prefix="cc_t5_")
        self.storage = ChatHistoryStorage(self._tmp, max_messages=50)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_wechat_uid_creates_subdirectory(self):
        uid = build_wechat_uid("acc1", "wxid_abc")
        path = self.storage._get_user_file(uid)
        # 期望 data/chat_history/wechat/acc1/wxid_abc.json
        assert path.name == "wxid_abc.json"
        assert path.parent.name == "acc1"
        assert path.parent.parent.name == "wechat"
        assert path.parent.parent.parent.name == "chat_history"

    def test_web_uid_creates_subdirectory(self):
        uid = build_web_uid("gf001")
        path = self.storage._get_user_file(uid)
        assert path.name == "gf001.json"
        assert path.parent.name == "web"
        assert path.parent.parent.name == "chat_history"

    def test_cli_uid_creates_subdirectory(self):
        uid = build_cli_uid()
        path = self.storage._get_user_file(uid)
        assert path.name == "local.json"
        assert path.parent.name == "cli"

    def test_api_uid_creates_subdirectory(self):
        uid = build_api_uid("user1")
        path = self.storage._get_user_file(uid)
        assert path.name == "user1.json"
        assert path.parent.name == "api"

    def test_legacy_uid_uses_flat_path(self):
        """旧 user_id（无 ::）走 legacy 路径，扁平文件。"""
        path = self.storage._get_user_file("web_user")
        assert path.name == "web_user.json"
        assert path.parent.name == "chat_history"

    def test_legacy_uid_stress_test_user_uses_flat_path(self):
        """test_stress_300_conversations.py 用的 'stress_test_user' 走 legacy 路径。"""
        path = self.storage._get_user_file("stress_test_user")
        assert path.name == "stress_test_user.json"
        assert path.parent.name == "chat_history"

    def test_wechat_subdir_actually_created_on_disk(self):
        """子目录在磁盘上真实创建（Windows 兼容验证）。"""
        uid = build_wechat_uid("acc1", "wxid_abc")
        path = self.storage._get_user_file(uid)
        assert path.parent.exists()
        assert path.parent.is_dir()

    def test_repeated_call_idempotent(self):
        """同一 uid 多次调用 _get_user_file 不报错（mkdir exist_ok=True）。"""
        uid = build_wechat_uid("acc1", "wxid_abc")
        path1 = self.storage._get_user_file(uid)
        path2 = self.storage._get_user_file(uid)
        assert path1 == path2


# ─────────────────────────────────────────────────────────────
# _get_user_file 路径穿越防护测试
# ─────────────────────────────────────────────────────────────


class TestGetUserFilePathTraversal:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp(prefix="cc_t5_traversal_")
        self.storage = ChatHistoryStorage(self._tmp, max_messages=50)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_wechat_account_id_path_traversal_rejected(self):
        """account_id 含 '..' 应被拒绝。"""
        # build_wechat_uid 不做校验，校验在 _get_user_file
        uid = f"wechat{SEP}..{SEP}passwd"
        with pytest.raises(ValueError, match="account_id"):
            self.storage._get_user_file(uid)

    def test_wechat_account_id_slash_rejected(self):
        uid = f"wechat{SEP}acc/evil{SEP}wxid"
        with pytest.raises(ValueError, match="account_id"):
            self.storage._get_user_file(uid)

    def test_wechat_account_id_backslash_rejected(self):
        uid = f"wechat{SEP}acc\\evil{SEP}wxid"
        with pytest.raises(ValueError, match="account_id"):
            self.storage._get_user_file(uid)

    def test_wechat_wxid_path_traversal_rejected(self):
        """wxid 含 '..' 应被拒绝（3 段格式 wechat::acc1::.. 触发 wechat 分支）。"""
        uid = f"wechat{SEP}acc1{SEP}.."
        with pytest.raises(ValueError, match="wxid"):
            self.storage._get_user_file(uid)

    def test_web_persona_id_path_traversal_rejected(self):
        """persona_id 含 '..' 应被拒绝（2 段格式 web::.. 触发 web 分支）。"""
        uid = f"web{SEP}.."
        with pytest.raises(ValueError, match="persona_id"):
            self.storage._get_user_file(uid)

    def test_api_user_id_path_traversal_rejected(self):
        """api user_id 含 '..' 应被拒绝（2 段格式 api::.. 触发 api 分支）。"""
        uid = f"api{SEP}.."
        with pytest.raises(ValueError, match="api user_id"):
            self.storage._get_user_file(uid)

    def test_legacy_path_traversal_sanitized_and_contained(self):
        """legacy 路径穿越防护：sanitize 把 / 替成 _，is_relative_to 保证路径不越界。

        注意：sanitize 允许 '.'，所以文件名中可能含 '..' 字面量，但它只是文件名
        的一部分（不是路径分隔符），且 is_relative_to 校验保证最终路径在 data_dir 内。
        """
        path = self.storage._get_user_file("../../../etc/passwd")
        # sanitize 后文件名不含路径分隔符（/ → _），落在 chat_history/ 根目录
        assert path.parent.name == "chat_history"
        # 关键安全保证：解析后路径仍在 data_dir 内
        assert path.is_relative_to(self.storage._data_dir.resolve())


# ─────────────────────────────────────────────────────────────
# add_message 携带新字段 round-trip 测试
# ─────────────────────────────────────────────────────────────


class TestAddMessageWithPlatformFields:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp(prefix="cc_t5_addmsg_")
        self.storage = ChatHistoryStorage(self._tmp, max_messages=50)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_add_message_with_all_new_fields_stored_and_loaded(self):
        uid = build_wechat_uid("acc1", "wxid_abc")
        self.storage.add_message(
            uid, "user", "hello",
            platform="wechat", persona_id="gf001", account_id="acc1",
        )
        msgs = self.storage.get_messages(uid)
        assert len(msgs) == 1
        msg = msgs[0]
        assert msg["role"] == "user"
        assert msg["content"] == "hello"
        assert msg["platform"] == "wechat"
        assert msg["persona_id"] == "gf001"
        assert msg["account_id"] == "acc1"
        assert "timestamp" in msg

    def test_add_message_without_new_fields_backward_compat(self):
        """旧调用不传 platform/persona_id/account_id，消息不含这些字段，不报错。"""
        uid = build_web_uid("gf001")
        # 模拟旧调用：只传 user_id, role, content
        self.storage.add_message(uid, "user", "legacy call")
        msgs = self.storage.get_messages(uid)
        assert len(msgs) == 1
        msg = msgs[0]
        assert msg["role"] == "user"
        assert msg["content"] == "legacy call"
        # 新字段不应存在（空字符串不写入）
        assert "platform" not in msg
        assert "persona_id" not in msg
        assert "account_id" not in msg

    def test_add_message_with_emotion_and_platform_fields(self):
        """add_message 同时携带 emotion 和 platform 字段。"""
        uid = build_wechat_uid("acc1", "wxid_abc")
        self.storage.add_message(
            uid, "user", "好开心",
            emotion="happy", emotion_intensity=0.8,
            emotion_understanding="用户表达了喜悦",
            platform="wechat", persona_id="gf001", account_id="acc1",
        )
        msgs = self.storage.get_messages(uid)
        msg = msgs[0]
        assert msg["emotion"] == "happy"
        assert msg["emotion_intensity"] == 0.8
        assert msg["emotion_understanding"] == "用户表达了喜悦"
        assert msg["platform"] == "wechat"
        assert msg["persona_id"] == "gf001"
        assert msg["account_id"] == "acc1"

    def test_add_message_persists_to_subdirectory_file(self):
        """消息持久化到正确的子目录文件。"""
        uid = build_wechat_uid("acc1", "wxid_abc")
        self.storage.add_message(
            uid, "user", "persisted",
            platform="wechat", persona_id="gf001", account_id="acc1",
        )
        filepath = self.storage._get_user_file(uid)
        assert filepath.exists()
        # 文件路径验证
        assert filepath.parent.name == "acc1"
        assert filepath.name == "wxid_abc.json"

    def test_add_message_assistant_role_with_platform_fields(self):
        """assistant 角色消息也携带 platform 字段。"""
        uid = build_web_uid("gf001")
        self.storage.add_message(
            uid, "assistant", "hi there",
            platform="web", persona_id="gf001",
        )
        msgs = self.storage.get_messages(uid)
        msg = msgs[0]
        assert msg["role"] == "assistant"
        assert msg["platform"] == "web"
        assert msg["persona_id"] == "gf001"
        # account_id 空字符串不写入
        assert "account_id" not in msg

    def test_load_legacy_message_without_platform_fields(self):
        """加载不含 platform 字段的旧消息不报错（向后兼容）。"""
        uid = build_web_uid("gf001")
        # 先以旧格式写入（不传新字段）
        self.storage.add_message(uid, "user", "old message")
        # 清缓存强制从磁盘加载
        self.storage._cache.clear()
        msgs = self.storage.get_messages(uid)
        assert len(msgs) == 1
        assert msgs[0]["content"] == "old message"
        # 旧消息不含新字段
        assert "platform" not in msgs[0]


# ─────────────────────────────────────────────────────────────
# 跨平台子目录隔离测试
# ─────────────────────────────────────────────────────────────


class TestCrossPlatformIsolation:
    def setup_method(self):
        self._tmp = tempfile.mkdtemp(prefix="cc_t5_iso_")
        self.storage = ChatHistoryStorage(self._tmp, max_messages=50)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_wechat_and_web_users_isolated(self):
        """微信用户和 WebUI 用户消息存入不同文件。"""
        wechat_uid = build_wechat_uid("acc1", "wxid_abc")
        web_uid = build_web_uid("gf001")

        self.storage.add_message(wechat_uid, "user", "wechat msg", platform="wechat")
        self.storage.add_message(web_uid, "user", "web msg", platform="web")

        wechat_msgs = self.storage.get_messages(wechat_uid)
        web_msgs = self.storage.get_messages(web_uid)

        assert len(wechat_msgs) == 1
        assert len(web_msgs) == 1
        assert wechat_msgs[0]["content"] == "wechat msg"
        assert web_msgs[0]["content"] == "web msg"

    def test_two_wechat_accounts_isolated(self):
        """同平台不同账号的消息存入不同子目录。"""
        uid_acc1 = build_wechat_uid("acc1", "wxid_abc")
        uid_acc2 = build_wechat_uid("acc2", "wxid_abc")

        self.storage.add_message(uid_acc1, "user", "msg from acc1", platform="wechat", account_id="acc1")
        self.storage.add_message(uid_acc2, "user", "msg from acc2", platform="wechat", account_id="acc2")

        assert self.storage.get_messages(uid_acc1)[0]["content"] == "msg from acc1"
        assert self.storage.get_messages(uid_acc2)[0]["content"] == "msg from acc2"

        # 验证文件路径不同
        path1 = self.storage._get_user_file(uid_acc1)
        path2 = self.storage._get_user_file(uid_acc2)
        assert path1 != path2
        assert path1.parent.name == "acc1"
        assert path2.parent.name == "acc2"

    def test_legacy_and_composite_coexist(self):
        """legacy user_id 和复合 user_id 共存，互不干扰。"""
        legacy_uid = "web_user"
        composite_uid = build_web_uid("gf001")

        self.storage.add_message(legacy_uid, "user", "legacy")
        self.storage.add_message(composite_uid, "user", "composite", platform="web", persona_id="gf001")

        assert self.storage.get_messages(legacy_uid)[0]["content"] == "legacy"
        assert self.storage.get_messages(composite_uid)[0]["content"] == "composite"

        # legacy 文件在 chat_history/ 根目录
        legacy_path = self.storage._get_user_file(legacy_uid)
        assert legacy_path.parent.name == "chat_history"
        # composite 文件在 chat_history/web/ 子目录
        composite_path = self.storage._get_user_file(composite_uid)
        assert composite_path.parent.name == "web"
