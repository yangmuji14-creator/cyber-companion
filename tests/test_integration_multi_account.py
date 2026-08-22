"""T12 Integration: multi-account isolation end-to-end.

Verifies the full multi-account + conversation isolation flows with real
components (ConversationStore, ChatHistoryStorage, WeChatAdapter) and mocked
SDK / pipeline. The weixin-ilink SDK is NEVER imported — inbound wechat
messages are simulated via the _FakeWeChatMsg pattern (T4 lesson #7).

Flows covered (per T12 plan):
1. Two WeChatAdapter(acc1, acc2) → distinct credential paths + user_ids.
2. Two wechat accounts → isolated chat histories (real ChatHistoryStorage
   with subdirectory storage, T5).
3. Two wechat accounts → isolated conversation bindings (real
   ConversationStore, T6).
4. Rebind: update_persona gf001 → gf002 → next message through
   _handle_message receives "gf002" (T7 binding lookup).
5. Web chat with persona gf001 → chat history stored under web/gf001.json,
   isolated from wechat histories (T5 subdirectory storage + T9 web uid).

SKIPPED flow (documented):
- Mood sharing across same-persona conversations: MoodEngine is keyed by
  user_id (see core/emotion/mood.py:223 get_mood(user_id)), NOT by
  persona_id. Mood is per-user, not per-persona — so "chat on web with
  gf001 updates mood, wechat msg with gf001 sees updated mood" does not
  reflect the actual API. The inherited wisdom's assumption
  ("update_mood(user_id, persona_id, emotion)") was wrong. Skipping per
  T12 MUST DO: "If MoodEngine doesn't exist or is hard to test, skip the
  mood sharing test and document."

Privacy: all IDs are placeholders (wxid_test_a, wxid_test_b, acc1, acc2,
gf001, gf002). No real wechat credentials or wxids.
"""

import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))

from adapters.base import AdapterMessage
from adapters.cli import CLIAdapter
from adapters.debounce import DebounceManager
from adapters.manager import AdapterManager
from adapters.wechat import WeChatAdapter
from core.config import DEFAULT_PERSONA_ID, build_web_uid, build_wechat_uid
from core.conversation import ConversationStore
from core.memory.chat_history import ChatHistoryStorage


# ════════════════════════════════════════════════════════════════
# Test helpers — _FakeWeChatMsg (T4 lesson #7 pattern)
# ════════════════════════════════════════════════════════════════


class _FakeWeChatMsg:
    """Minimal fake weixin-ilink message object.

    Only implements the attributes that WeChatAdapter._on_inbound_message
    actually accesses: from_user, text, message_id, context_token,
    reply_typing, reply_text. wxid values are placeholders.
    """

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


async def _drive_inbound(adapter: WeChatAdapter, msg) -> list[str]:
    """Drive _on_inbound_message and capture user_ids passed to the handler.

    Returns the list of user_ids the handler received (one per call).
    Handler returns "" so _send_segmented is skipped.
    """
    captured: list[str] = []

    async def _capture(message: AdapterMessage) -> str:
        captured.append(message.user_id)
        return ""

    adapter.set_handler(_capture)
    await adapter._on_inbound_message(msg)
    return captured


# ════════════════════════════════════════════════════════════════
# Fixture — capture _handle_message closure (T7 lesson #1 pattern)
# ════════════════════════════════════════════════════════════════


def _make_minimal_app(tmp_path, pipeline):
    """Build a minimal AppComponents for run_with_adapters.

    Uses real ConversationStore (tmp_path-backed) so rebind tests can
    observe binding state changes through the real CRUD path.
    """
    return SimpleNamespace(
        handler=SimpleNamespace(pipeline=pipeline),
        advanced_config={"debounce_seconds": 3},
        conversation_store=ConversationStore(tmp_path / "conversations.json"),
        vision_manager=None,
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


class _CapturingPipeline:
    """Fake pipeline that records (user_id, content, persona_id) per call."""

    def __init__(self):
        self.calls: list[tuple[str, str, str]] = []

    async def process(self, user_id, content, persona_id, **kwargs):
        self.calls.append((user_id, content, persona_id))
        return ("reply", 0)


@pytest.fixture
async def captured_handler(tmp_path):
    """Capture the _handle_message closure from run_with_adapters.

    Yields (handler, app, pipeline, debounce_calls) where:
    - handler: the captured _handle_message closure
    - app: the minimal AppComponents (conversation_store is real)
    - pipeline: _CapturingPipeline (for image-path assertions)
    - debounce_calls: list of (platform, user_id, text, persona_id)

    Patches stay active for the duration of the test (fixture yields).
    Pattern comes from T7 lesson #1: patch set_message_handler to capture
    the closure, mock CLI to /quit immediately, noop start_all/stop_all/
    flush_all, and intercept debounce.add_message.
    """
    from core.app import run_with_adapters

    pipeline = _CapturingPipeline()
    app = _make_minimal_app(tmp_path, pipeline)

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


def _make_wechat_msg(account_id: str, wxid: str, content: str = "hello") -> AdapterMessage:
    """Build an AdapterMessage simulating an inbound wechat message."""
    return AdapterMessage(
        user_id=build_wechat_uid(account_id, wxid),
        content=content,
        platform="wechat",
        account_id=account_id,
        metadata={},
    )


# ════════════════════════════════════════════════════════════════
# Tests
# ════════════════════════════════════════════════════════════════


async def test_two_adapters_produce_isolated_user_ids_and_credential_paths():
    """Flow 1: 2 WeChatAdapter(acc1, acc2) → distinct credential paths + user_ids.

    Same wxid on two accounts produces different user_ids
    (wechat::acc1::wxid_test_a vs wechat::acc2::wxid_test_b) and different
    credential file paths (wechat_acc1.json vs wechat_acc2.json).
    """
    a1 = WeChatAdapter(account_id="acc1")
    a2 = WeChatAdapter(account_id="acc2")

    # Credential paths are isolated (T4 lesson #1)
    assert a1._credentials_file.name == "wechat_acc1.json"
    assert a2._credentials_file.name == "wechat_acc2.json"
    assert a1._credentials_file != a2._credentials_file
    assert a1._sync_file != a2._sync_file

    # Inbound messages produce isolated user_ids (T4 lesson #6)
    msg_a = _FakeWeChatMsg(from_user="wxid_test_a", text="hello from A")
    msg_b = _FakeWeChatMsg(from_user="wxid_test_b", text="hello from B")

    cap_a = await _drive_inbound(a1, msg_a)
    cap_b = await _drive_inbound(a2, msg_b)

    assert cap_a == ["wechat::acc1::wxid_test_a"]
    assert cap_b == ["wechat::acc2::wxid_test_b"]
    assert cap_a[0] != cap_b[0]


def test_two_wechat_accounts_have_isolated_chat_histories(tmp_path):
    """Flow 2: add_message to acc1/wxid_A → get_messages shows it; acc2/wxid_B empty.

    Uses real ChatHistoryStorage with subdirectory storage (T5). Verifies
    that messages from two wechat accounts land in different files
    (wechat/acc1/wxid_A.json vs wechat/acc2/wxid_B.json) and don't
    cross-contaminate.
    """
    storage = ChatHistoryStorage(tmp_path, max_messages=50)

    uid_a = build_wechat_uid("acc1", "wxid_test_a")
    uid_b = build_wechat_uid("acc2", "wxid_test_b")

    # Add a message only for acc1/wxid_A
    storage.add_message(
        uid_a, "user", "hello from acc1",
        platform="wechat", persona_id="gf001", account_id="acc1",
    )

    # acc1/wxid_A has the message
    msgs_a = storage.get_messages(uid_a)
    assert len(msgs_a) == 1
    assert msgs_a[0]["content"] == "hello from acc1"
    assert msgs_a[0]["platform"] == "wechat"
    assert msgs_a[0]["account_id"] == "acc1"

    # acc2/wxid_B history is empty
    msgs_b = storage.get_messages(uid_b)
    assert msgs_b == []

    # Files are in different subdirectories (T5 subdirectory storage)
    path_a = storage._get_user_file(uid_a)
    path_b = storage._get_user_file(uid_b)
    assert path_a != path_b
    assert path_a.parent.name == "acc1"
    assert path_b.parent.name == "acc2"
    assert path_a.parent.parent.name == "wechat"
    assert path_b.parent.parent.name == "wechat"

    # Only acc1's file exists on disk (acc2 was never written)
    assert path_a.exists()
    assert not path_b.exists()


def test_two_wechat_accounts_have_isolated_conversation_bindings(tmp_path):
    """Flow 3: ConversationStore.find('wechat','acc1','wxid_A') != find('wechat','acc2','wxid_B').

    Uses real ConversationStore (T6). Verifies that two wechat accounts
    get distinct conversation bindings with distinct conversation_ids.
    """
    store = ConversationStore(tmp_path / "conversations.json")

    b1 = store.create("wechat", "acc1", "wxid_test_a", "gf001")
    b2 = store.create("wechat", "acc2", "wxid_test_b", "gf001")

    # Distinct conversation_ids
    assert b1.conversation_id != b2.conversation_id
    assert b1.conversation_id == "conv_1"
    assert b2.conversation_id == "conv_2"

    # find returns the correct binding per (platform, account_id, contact_id)
    found1 = store.find("wechat", "acc1", "wxid_test_a")
    found2 = store.find("wechat", "acc2", "wxid_test_b")
    assert found1 is b1 or found1.conversation_id == "conv_1"
    assert found2 is b2 or found2.conversation_id == "conv_2"
    assert found1.conversation_id != found2.conversation_id

    # Cross-account find returns None (no leakage)
    assert store.find("wechat", "acc1", "wxid_test_b") is None
    assert store.find("wechat", "acc2", "wxid_test_a") is None

    # list_by_platform returns both
    all_wechat = store.list_by_platform("wechat")
    assert len(all_wechat) == 2
    assert {b.account_id for b in all_wechat} == {"acc1", "acc2"}


async def test_rebind_persona_takes_effect_on_next_message(captured_handler):
    """Flow 4: update_persona acc1/wxid_A from gf001 to gf002 → next msg receives 'gf002'.

    Integration: _handle_message reads binding from ConversationStore
    (T7), so rebind via update_persona takes effect on the next inbound
    message. Verifies the full chain: binding create → msg → debounce
    receives gf001 → rebind → msg → debounce receives gf002.
    """
    handler, app, _pipeline, debounce_calls = captured_handler

    # Pre-create binding with persona gf001
    app.conversation_store.create(
        "wechat", "acc1", "wxid_test_a", persona_id="gf001",
    )

    # First message → debounce should receive gf001
    msg = _make_wechat_msg("acc1", "wxid_test_a", "first message")
    await handler(msg)
    assert len(debounce_calls) == 1
    assert debounce_calls[0][3] == "gf001"

    # Rebind: gf001 → gf002
    binding = app.conversation_store.find("wechat", "acc1", "wxid_test_a")
    assert binding is not None
    updated = app.conversation_store.update_persona(
        binding.conversation_id, "gf002",
    )
    assert updated.persona_id == "gf002"

    # Second message → debounce should receive gf002 (rebind took effect)
    await handler(msg)
    assert len(debounce_calls) == 2
    assert debounce_calls[1][3] == "gf002"

    # acc1/wxid_A always routes to the same user_id (rebind doesn't change routing)
    assert debounce_calls[0][1] == debounce_calls[1][1]
    assert debounce_calls[0][1] == "wechat::acc1::wxid_test_a"


async def test_rebind_does_not_affect_other_account(captured_handler):
    """Flow 4b: rebinding acc1/wxid_A to gf002 does NOT change acc2/wxid_B.

    Integration: rebind is per-binding (per (platform, account_id, contact_id)
    triple). Acc2's binding keeps its original persona_id.
    """
    handler, app, _pipeline, debounce_calls = captured_handler

    # Two accounts, both initially gf001
    b1 = app.conversation_store.create(
        "wechat", "acc1", "wxid_test_a", persona_id="gf001",
    )
    app.conversation_store.create(
        "wechat", "acc2", "wxid_test_b", persona_id="gf001",
    )

    # Rebind acc1 to gf002
    app.conversation_store.update_persona(b1.conversation_id, "gf002")

    # Message from acc1 → gf002
    msg_a = _make_wechat_msg("acc1", "wxid_test_a", "from acc1")
    await handler(msg_a)
    assert debounce_calls[-1][3] == "gf002"

    # Message from acc2 → still gf001 (unaffected by acc1's rebind)
    msg_b = _make_wechat_msg("acc2", "wxid_test_b", "from acc2")
    await handler(msg_b)
    assert debounce_calls[-1][3] == "gf001"
    assert debounce_calls[-1][1] == "wechat::acc2::wxid_test_b"


def test_web_chat_history_isolated_from_wechat(tmp_path):
    """Flow 5: web chat with persona gf001 → history in web/gf001.json, isolated from wechat.

    Integration: ChatHistoryStorage subdirectory storage (T5) routes
    web::gf001 to web/gf001.json and wechat::acc1::wxid_A to
    wechat/acc1/wxid_A.json. Same persona (gf001) on two platforms
    produces two distinct history files — persona is shared in spirit
    but conversation history is per-user_id.
    """
    storage = ChatHistoryStorage(tmp_path, max_messages=50)

    web_uid = build_web_uid("gf001")
    wechat_uid = build_wechat_uid("acc1", "wxid_test_a")

    # Simulate web chat with persona gf001
    storage.add_message(
        web_uid, "user", "hello from web",
        platform="web", persona_id="gf001",
    )
    # Simulate wechat message with same persona gf001
    storage.add_message(
        wechat_uid, "user", "hello from wechat",
        platform="wechat", persona_id="gf001", account_id="acc1",
    )

    # Histories are isolated
    web_msgs = storage.get_messages(web_uid)
    wechat_msgs = storage.get_messages(wechat_uid)
    assert len(web_msgs) == 1
    assert len(wechat_msgs) == 1
    assert web_msgs[0]["content"] == "hello from web"
    assert wechat_msgs[0]["content"] == "hello from wechat"

    # Files are in different subdirectories (web vs wechat/acc1)
    web_path = storage._get_user_file(web_uid)
    wechat_path = storage._get_user_file(wechat_uid)
    assert web_path != wechat_path
    assert web_path.parent.name == "web"
    assert wechat_path.parent.name == "acc1"
    assert wechat_path.parent.parent.name == "wechat"
    assert web_path.parent.parent.name == "chat_history"

    # Both files exist on disk (auto-created by add_message)
    assert web_path.exists()
    assert wechat_path.exists()


async def test_first_wechat_message_auto_creates_binding_with_default_persona(
    captured_handler,
):
    """Flow 6 (bonus): first wechat msg from a new wxid auto-creates a binding.

    Integration: T7 _handle_message auto-creates a ConversationBinding
    with DEFAULT_PERSONA_ID when no binding exists. Verifies the binding
    is created in the real ConversationStore and the next find() returns
    it with the default persona.
    """
    handler, app, _pipeline, debounce_calls = captured_handler

    # No pre-existing binding
    assert app.conversation_store.find("wechat", "acc1", "wxid_new") is None

    msg = _make_wechat_msg("acc1", "wxid_new", "first ever message")
    await handler(msg)

    # Binding was auto-created with DEFAULT_PERSONA_ID
    binding = app.conversation_store.find("wechat", "acc1", "wxid_new")
    assert binding is not None
    assert binding.persona_id == DEFAULT_PERSONA_ID

    # Debounce received DEFAULT_PERSONA_ID (not gf001/gf002)
    assert len(debounce_calls) == 1
    assert debounce_calls[0][3] == DEFAULT_PERSONA_ID


# ════════════════════════════════════════════════════════════════
# SKIPPED: Mood sharing across same-persona conversations
# ════════════════════════════════════════════════════════════════


def test_mood_sharing_skipped_documentation():
    """SKIPPED: mood sharing across same-persona conversations.

    The T12 plan specified: "chat on web with gf001 → mood updates →
    wechat msg with gf001 (same persona) sees updated mood (shared
    persona state, not shared conversation)".

    This flow is NOT testable with the current MoodEngine API because
    MoodEngine is keyed by user_id, NOT by persona_id:

        # core/emotion/mood.py:223
        def get_mood(self, user_id: str) -> MoodState: ...

        # core/emotion/mood.py:234
        def update_from_emotion(self, user_id: str, emotion: EmotionResult) -> MoodState: ...

    There is no persona_id parameter. Mood is per-user_id, so
    web::gf001 and wechat::acc1::wxid_A have independent moods even
    though both conversations use persona gf001. The inherited wisdom's
    assumption ("update_mood(user_id, persona_id, emotion)") was
    incorrect — the actual API is update_from_emotion(user_id, emotion).

    To implement persona-scoped mood sharing, MoodEngine would need to
    be re-keyed by persona_id (or by a (user_id, persona_id) tuple).
    That is a design change outside T12's test-only scope.

    This test is a no-op that documents the skip decision. It passes
    by assertion, ensuring the skip is visible in the test report.
    """
    # If MoodEngine ever gains a persona_id parameter, this test should
    # be replaced with a real mood-sharing integration test.
    from core.emotion.mood import MoodEngine
    import inspect
    sig = inspect.signature(MoodEngine.update_from_emotion)
    assert "persona_id" not in sig.parameters, (
        "MoodEngine.update_from_emotion now accepts persona_id — "
        "replace this skip test with a real mood-sharing integration test."
    )
