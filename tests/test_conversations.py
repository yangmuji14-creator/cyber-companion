"""ConversationStore + /api/conversations route tests.

Covers:
- ConversationBinding.from_dict / to_dict round-trip + 缺失字段容错
- ConversationStore CRUD round-trip (create → get → list → update_persona → delete)
- 三元组唯一约束 (create 重复 → ValueError)
- find(platform, account_id, contact_id) 命中 / 未命中
- list_by_platform
- next_id 自增 + 持久化恢复
- 并发 create (2 线程) RLock 保护无数据丢失
- API routes: POST/GET/PATCH/DELETE + 404/409 边界

隐私: 所有 ID 用占位符 (wxid_test, acc1, gf001, web_user)，不含真实账号。
"""

import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from aiohttp.test_utils import TestClient, TestServer

import webui.server as srv
from core.conversation import ConversationBinding, ConversationStore
from core.persona.models import Persona

from tests.test_webui import FakeAppComponents, FakePersonaLoader


# ════════════════════════════════════════════════════════════════
# ConversationBinding
# ════════════════════════════════════════════════════════════════

def test_binding_from_dict_to_dict_round_trip():
    """to_dict ∘ from_dict = identity for fully-populated dict."""
    d = {
        "conversation_id": "conv_1",
        "platform": "wechat",
        "account_id": "acc1",
        "contact_id": "wxid_test",
        "persona_id": "gf001",
        "created_at": "2026-07-18T10:00:00",
        "updated_at": "2026-07-18T10:00:00",
        "title": "小红的聊天",
    }
    b = ConversationBinding.from_dict(d)
    assert b.to_dict() == d


def test_binding_from_dict_missing_fields_uses_defaults():
    """缺失字段用默认值（向后兼容旧数据）。"""
    b = ConversationBinding.from_dict({"conversation_id": "conv_1"})
    assert b.platform == ""
    assert b.account_id == ""
    assert b.contact_id == ""
    assert b.persona_id == ""
    assert b.created_at == ""
    assert b.updated_at == ""
    assert b.title == ""


def test_binding_from_dict_missing_title_defaults_empty():
    """旧数据无 title 字段 → from_dict 默认 ""（向后兼容）。"""
    d = {
        "conversation_id": "conv_1",
        "platform": "wechat",
        "account_id": "acc1",
        "contact_id": "wxid_test",
        "persona_id": "gf001",
        "created_at": "2026-07-18T10:00:00",
        "updated_at": "2026-07-18T10:00:00",
    }
    b = ConversationBinding.from_dict(d)
    assert b.title == ""
    # to_dict 会写出 title=""（新格式），旧 dict 加上 title 字段后应相等
    d["title"] = ""
    assert b.to_dict() == d


# ════════════════════════════════════════════════════════════════
# ConversationStore — fixtures
# ════════════════════════════════════════════════════════════════

@pytest.fixture
def store(tmp_path):
    """Fresh ConversationStore backed by tmp_path/conversations.json."""
    return ConversationStore(tmp_path / "conversations.json")


# ════════════════════════════════════════════════════════════════
# ConversationStore — CRUD round-trip
# ════════════════════════════════════════════════════════════════

def test_create_get_list_update_delete_round_trip(store):
    """完整 CRUD round-trip: create → get → list → update_persona → delete."""
    # create
    b = store.create("wechat", "acc1", "wxid_test", "gf001")
    assert b.conversation_id == "conv_1"
    assert b.platform == "wechat"
    assert b.persona_id == "gf001"
    assert b.created_at != ""
    assert b.updated_at == b.created_at

    # get
    fetched = store.get("conv_1")
    assert fetched is b or fetched.conversation_id == "conv_1"

    # list
    all_bindings = store.list()
    assert len(all_bindings) == 1
    assert all_bindings[0].conversation_id == "conv_1"

    # update_persona
    updated = store.update_persona("conv_1", "gf002")
    assert updated.persona_id == "gf002"
    assert updated.updated_at >= updated.created_at

    # delete
    assert store.delete("conv_1") is True
    assert store.get("conv_1") is None
    assert store.list() == []


def test_create_duplicate_triple_raises_value_error(store):
    """三元组 (platform, account_id, contact_id) 重复 → ValueError。"""
    store.create("wechat", "acc1", "wxid_test", "gf001")
    with pytest.raises(ValueError, match="already exists"):
        store.create("wechat", "acc1", "wxid_test", "gf002")


def test_create_same_contact_different_platform_ok(store):
    """同 contact_id 不同 platform → 不同 binding，不冲突。"""
    b1 = store.create("wechat", "acc1", "wxid_test", "gf001")
    b2 = store.create("web", "", "wxid_test", "gf001")
    assert b1.conversation_id != b2.conversation_id
    assert len(store.list()) == 2


def test_find_by_triple_returns_binding(store):
    """find 命中三元组返回 binding。"""
    store.create("wechat", "acc1", "wxid_test", "gf001")
    found = store.find("wechat", "acc1", "wxid_test")
    assert found is not None
    assert found.conversation_id == "conv_1"
    assert found.persona_id == "gf001"


def test_find_by_triple_returns_none_when_missing(store):
    """find 未命中返回 None。"""
    assert store.find("wechat", "acc1", "wxid_test") is None


def test_list_by_platform(store):
    """list_by_platform 返回某平台所有 binding。"""
    store.create("wechat", "acc1", "wxid_a", "gf001")
    store.create("wechat", "acc2", "wxid_b", "gf001")
    store.create("web", "", "web_user", "gf001")

    wechat_bindings = store.list_by_platform("wechat")
    assert len(wechat_bindings) == 2
    assert all(b.platform == "wechat" for b in wechat_bindings)

    web_bindings = store.list_by_platform("web")
    assert len(web_bindings) == 1
    assert web_bindings[0].contact_id == "web_user"


def test_next_id_increments(store):
    """next_id 随 create 自增，删除不回收。"""
    b1 = store.create("wechat", "acc1", "wxid_a", "gf001")
    b2 = store.create("wechat", "acc1", "wxid_b", "gf001")
    b3 = store.create("wechat", "acc1", "wxid_c", "gf001")
    assert (b1.conversation_id, b2.conversation_id, b3.conversation_id) == (
        "conv_1", "conv_2", "conv_3"
    )
    # 删除中间一条，下一条仍是 conv_4（不回收）
    store.delete("conv_2")
    b4 = store.create("wechat", "acc1", "wxid_d", "gf001")
    assert b4.conversation_id == "conv_4"


def test_update_persona_returns_none_when_missing(store):
    """update_persona 不存在 → None。"""
    assert store.update_persona("conv_999", "gf002") is None


def test_rename_updates_title_and_timestamp(store):
    """rename 更新 title + updated_at，返回 binding。"""
    b = store.create("wechat", "acc1", "wxid_test", "gf001")
    assert b.title == ""  # 默认空
    old_updated = b.updated_at
    renamed = store.rename("conv_1", "小红的聊天")
    assert renamed is not None
    assert renamed.title == "小红的聊天"
    assert renamed.updated_at >= old_updated
    # 持久化：重新加载应保留 title
    assert store.get("conv_1").title == "小红的聊天"


def test_rename_clear_title_with_empty_string(store):
    """rename 传空串清除 title（回退显示 persona name）。"""
    store.create("wechat", "acc1", "wxid_test", "gf001")
    store.rename("conv_1", "小红的聊天")
    assert store.get("conv_1").title == "小红的聊天"
    cleared = store.rename("conv_1", "")
    assert cleared is not None
    assert cleared.title == ""


def test_rename_returns_none_when_missing(store):
    """rename 不存在 → None。"""
    assert store.rename("conv_999", "不存在") is None


def test_delete_returns_false_when_missing(store):
    """delete 不存在 → False。"""
    assert store.delete("conv_999") is False


# ════════════════════════════════════════════════════════════════
# ConversationStore — 持久化
# ════════════════════════════════════════════════════════════════

def test_load_recovers_cache_and_next_id(tmp_path):
    """重启后从 JSON 恢复 cache + next_id。"""
    f = tmp_path / "conversations.json"
    s1 = ConversationStore(f)
    s1.create("wechat", "acc1", "wxid_a", "gf001")
    s1.create("wechat", "acc1", "wxid_b", "gf002")
    s1.delete("conv_1")  # 制造空洞，验证 next_id 不回收

    # 新实例模拟重启
    s2 = ConversationStore(f)
    assert len(s2.list()) == 1
    assert s2.list()[0].conversation_id == "conv_2"
    # 下一条应是 conv_3，不是 conv_1
    b = s2.create("wechat", "acc1", "wxid_c", "gf001")
    assert b.conversation_id == "conv_3"


def test_load_empty_file_starts_at_conv_1(tmp_path):
    """无文件 / 空文件 → 从 conv_1 开始。"""
    s = ConversationStore(tmp_path / "nonexistent.json")
    b = s.create("web", "", "web_user", "gf001")
    assert b.conversation_id == "conv_1"


# ════════════════════════════════════════════════════════════════
# ConversationStore — 并发
# ════════════════════════════════════════════════════════════════

def test_concurrent_create_no_data_loss(store):
    """2 线程同时 create 不同三元组 → 都成功，无数据丢失（RLock 保护）。

    用 barrier 同步起跑，最大化竞争窗口。
    """
    n_threads = 8
    barrier = threading.Barrier(n_threads)
    results: list = []
    lock = threading.Lock()

    def worker(idx: int):
        barrier.wait()  # 所有线程同时起跑
        b = store.create("wechat", f"acc{idx}", f"wxid_{idx}", "gf001")
        with lock:
            results.append(b.conversation_id)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 所有线程都成功
    assert len(results) == n_threads
    # conversation_id 唯一无重复
    assert len(set(results)) == n_threads
    # 缓存与持久化一致
    assert len(store.list()) == n_threads
    # next_id 推进到正确位置
    expected_next = max(int(r.removeprefix("conv_")) for r in results) + 1
    next_b = store.create("web", "", "web_user_after", "gf001")
    assert int(next_b.conversation_id.removeprefix("conv_")) == expected_next


def test_concurrent_duplicate_create_only_one_wins(store):
    """多线程并发创建相同三元组 → 仅 1 个成功，其余 ValueError。"""
    n_threads = 8
    barrier = threading.Barrier(n_threads)
    successes: list = []
    failures: list = []
    lock = threading.Lock()

    def worker():
        barrier.wait()
        try:
            store.create("wechat", "acc1", "wxid_same", "gf001")
            with lock:
                successes.append(1)
        except ValueError:
            with lock:
                failures.append(1)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(successes) == 1
    assert len(failures) == n_threads - 1
    assert len(store.list()) == 1


# ════════════════════════════════════════════════════════════════
# /api/conversations routes
# ════════════════════════════════════════════════════════════════

@pytest.fixture
async def api(tmp_path, monkeypatch):
    """Yield (TestClient, FakeAppComponents) with real ConversationStore.

    ConversationStore points at tmp_path/conversations.json — fully isolated.
    """
    monkeypatch.setattr(srv, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(srv, "AVATAR_DIR", tmp_path / "avatars")
    # T13: isolate migration marker + legacy file checks to tmp_path
    monkeypatch.setattr(srv, "DATA_DIR", tmp_path)

    components = FakeAppComponents()
    components.conversation_store = ConversationStore(tmp_path / "conversations.json")
    # FakePersonaLoader.get returns Persona with .name
    components.persona_loader.add_test_persona("gf001", "小雨")
    components.persona_loader.add_test_persona("gf002", "小雪")

    app = srv._make_app(components)
    server = TestServer(app)
    cli = TestClient(server)
    await cli.start_server()
    try:
        yield cli, components
    finally:
        await cli.close()


async def test_api_post_conversation_200(api):
    """POST /api/conversations 创建 binding → 200 + binding dict。"""
    client, _ = api
    resp = await client.post("/api/conversations", json={
        "platform": "wechat",
        "account_id": "acc1",
        "contact_id": "wxid_test",
        "persona_id": "gf001",
    })
    assert resp.status == 200
    data = await resp.json()
    assert data["conversation_id"] == "conv_1"
    assert data["platform"] == "wechat"
    assert data["persona_id"] == "gf001"
    assert data["created_at"] != ""


async def test_api_post_web_conversation_defaults_contact_to_persona(api):
    """网页会话无需暴露 contact_id，服务端生成稳定的 persona 级标识。"""
    client, _ = api
    resp = await client.post("/api/conversations", json={
        "platform": "web",
        "persona_id": "gf001",
    })

    assert resp.status == 200
    data = await resp.json()
    assert data["platform"] == "web"
    assert data["account_id"] == ""
    assert data["contact_id"] == "gf001"


async def test_api_post_wechat_conversation_still_requires_contact(api):
    """微信主动绑定必须有真实目标，避免创建无法发送消息的空绑定。"""
    client, _ = api
    resp = await client.post("/api/conversations", json={
        "platform": "wechat",
        "account_id": "acc1",
        "persona_id": "gf001",
    })

    assert resp.status == 400
    assert "contact_id" in (await resp.json())["error"]


async def test_api_get_conversations_list_200(api):
    """GET /api/conversations 返回列表，每条附带 persona_name。"""
    client, _ = api
    await client.post("/api/conversations", json={
        "platform": "wechat", "account_id": "acc1",
        "contact_id": "wxid_test", "persona_id": "gf001",
    })
    resp = await client.get("/api/conversations")
    assert resp.status == 200
    data = await resp.json()
    assert len(data) == 1
    assert data[0]["persona_name"] == "小雨"
    assert data[0]["conversation_id"] == "conv_1"


async def test_api_get_conversation_detail_200(api):
    """GET /api/conversations/{id} 返回单条详情。"""
    client, _ = api
    post = await client.post("/api/conversations", json={
        "platform": "wechat", "account_id": "acc1",
        "contact_id": "wxid_test", "persona_id": "gf001",
    })
    conv_id = (await post.json())["conversation_id"]

    resp = await client.get(f"/api/conversations/{conv_id}")
    assert resp.status == 200
    data = await resp.json()
    assert data["conversation_id"] == conv_id
    assert data["persona_name"] == "小雨"


async def test_api_get_conversation_detail_404(api):
    """GET /api/conversations/{id} 不存在 → 404。"""
    client, _ = api
    resp = await client.get("/api/conversations/conv_999")
    assert resp.status == 404


async def test_api_patch_conversation_200(api):
    """PATCH /api/conversations/{id} 更新 persona_id → 200。"""
    client, _ = api
    post = await client.post("/api/conversations", json={
        "platform": "wechat", "account_id": "acc1",
        "contact_id": "wxid_test", "persona_id": "gf001",
    })
    conv_id = (await post.json())["conversation_id"]

    resp = await client.patch(f"/api/conversations/{conv_id}", json={
        "persona_id": "gf002",
    })
    assert resp.status == 200
    data = await resp.json()
    assert data["persona_id"] == "gf002"


async def test_api_patch_conversation_404(api):
    """PATCH /api/conversations/{id} 不存在 → 404。"""
    client, _ = api
    resp = await client.patch("/api/conversations/conv_999", json={
        "persona_id": "gf002",
    })
    assert resp.status == 404


async def test_api_delete_conversation_200(api):
    """DELETE /api/conversations/{id} → 200 + {ok: true}。"""
    client, _ = api
    post = await client.post("/api/conversations", json={
        "platform": "wechat", "account_id": "acc1",
        "contact_id": "wxid_test", "persona_id": "gf001",
    })
    conv_id = (await post.json())["conversation_id"]

    resp = await client.delete(f"/api/conversations/{conv_id}")
    assert resp.status == 200
    data = await resp.json()
    assert data == {"ok": True}

    # 确认已删除
    resp2 = await client.get(f"/api/conversations/{conv_id}")
    assert resp2.status == 404


async def test_api_delete_conversation_404(api):
    """DELETE /api/conversations/{id} 不存在 → 404。"""
    client, _ = api
    resp = await client.delete("/api/conversations/conv_999")
    assert resp.status == 404


async def test_api_post_duplicate_409(api):
    """POST 重复三元组 → 409。"""
    client, _ = api
    body = {
        "platform": "wechat", "account_id": "acc1",
        "contact_id": "wxid_test", "persona_id": "gf001",
    }
    resp1 = await client.post("/api/conversations", json=body)
    assert resp1.status == 200

    resp2 = await client.post("/api/conversations", json=body)
    assert resp2.status == 409
    data = await resp2.json()
    assert "already exists" in data["error"]


async def test_api_post_invalid_body_400(api):
    """POST 缺少必填字段 → 400。"""
    client, _ = api
    resp = await client.post("/api/conversations", json={
        "platform": "wechat",
        # missing contact_id, persona_id
    })
    assert resp.status == 400


async def test_api_post_invalid_json_400(api):
    """POST 非 JSON body → 400。"""
    client, _ = api
    resp = await client.post(
        "/api/conversations",
        data="not json",
        headers={"Content-Type": "text/plain"},
    )
    assert resp.status == 400


async def test_api_patch_invalid_json_400(api):
    """PATCH 非 JSON body → 400。"""
    client, _ = api
    resp = await client.patch(
        "/api/conversations/conv_1",
        data="not json",
        headers={"Content-Type": "text/plain"},
    )
    assert resp.status == 400


async def test_api_patch_missing_persona_id_400(api):
    """PATCH 既无 persona_id 又无 title → 400。"""
    client, _ = api
    resp = await client.patch("/api/conversations/conv_1", json={})
    assert resp.status == 400


async def test_api_full_crud_round_trip(api):
    """API 层完整 CRUD round-trip。"""
    client, _ = api

    # POST
    post = await client.post("/api/conversations", json={
        "platform": "web", "account_id": "",
        "contact_id": "web_user", "persona_id": "gf001",
    })
    assert post.status == 200
    conv_id = (await post.json())["conversation_id"]

    # GET list
    lst = await client.get("/api/conversations")
    assert lst.status == 200
    assert len(await lst.json()) == 1

    # GET detail
    detail = await client.get(f"/api/conversations/{conv_id}")
    assert detail.status == 200

    # PATCH
    patched = await client.patch(f"/api/conversations/{conv_id}", json={
        "persona_id": "gf002",
    })
    assert patched.status == 200
    assert (await patched.json())["persona_id"] == "gf002"

    # DELETE
    deleted = await client.delete(f"/api/conversations/{conv_id}")
    assert deleted.status == 200

    # GET detail → 404
    after = await client.get(f"/api/conversations/{conv_id}")
    assert after.status == 404


# ════════════════════════════════════════════════════════════════
# /api/conversations PATCH title + DELETE chat_history cleanup
# ════════════════════════════════════════════════════════════════

async def test_api_patch_conversation_title_only_200(api):
    """PATCH 仅传 title → 200，binding.title 更新。"""
    client, _ = api
    post = await client.post("/api/conversations", json={
        "platform": "wechat", "account_id": "acc1",
        "contact_id": "wxid_test", "persona_id": "gf001",
    })
    conv_id = (await post.json())["conversation_id"]

    resp = await client.patch(f"/api/conversations/{conv_id}", json={
        "title": "小红的聊天",
    })
    assert resp.status == 200
    data = await resp.json()
    assert data["title"] == "小红的聊天"
    assert data["persona_id"] == "gf001"  # persona 未变


async def test_api_patch_conversation_title_and_persona_200(api):
    """PATCH 同时传 title + persona_id → 两者都更新。"""
    client, _ = api
    post = await client.post("/api/conversations", json={
        "platform": "wechat", "account_id": "acc1",
        "contact_id": "wxid_test", "persona_id": "gf001",
    })
    conv_id = (await post.json())["conversation_id"]

    resp = await client.patch(f"/api/conversations/{conv_id}", json={
        "title": "新备注", "persona_id": "gf002",
    })
    assert resp.status == 200
    data = await resp.json()
    assert data["title"] == "新备注"
    assert data["persona_id"] == "gf002"


async def test_api_patch_conversation_clear_title_200(api):
    """PATCH title="" → 清除备注名（回退显示 persona name）。"""
    client, _ = api
    post = await client.post("/api/conversations", json={
        "platform": "wechat", "account_id": "acc1",
        "contact_id": "wxid_test", "persona_id": "gf001",
    })
    conv_id = (await post.json())["conversation_id"]
    # 先设非空 title
    await client.patch(f"/api/conversations/{conv_id}", json={"title": "有备注"})
    # 再清除
    resp = await client.patch(f"/api/conversations/{conv_id}", json={"title": ""})
    assert resp.status == 200
    assert (await resp.json())["title"] == ""


async def test_api_patch_conversation_title_not_found_404(api):
    """PATCH title 到不存在的 conversation → 404。"""
    client, _ = api
    resp = await client.patch("/api/conversations/conv_999", json={"title": "x"})
    assert resp.status == 404


async def test_api_patch_conversation_empty_persona_id_with_title_200(api):
    """PATCH persona_id="" 但有 title → 只更新 title（persona_id 空串视为未提供）。"""
    client, _ = api
    post = await client.post("/api/conversations", json={
        "platform": "wechat", "account_id": "acc1",
        "contact_id": "wxid_test", "persona_id": "gf001",
    })
    conv_id = (await post.json())["conversation_id"]

    resp = await client.patch(f"/api/conversations/{conv_id}", json={
        "persona_id": "", "title": "仅改名",
    })
    assert resp.status == 200
    data = await resp.json()
    assert data["title"] == "仅改名"
    assert data["persona_id"] == "gf001"  # 未被空串覆盖


async def test_api_delete_conversation_cleans_chat_history(api):
    """DELETE 同时清 chat_history（按 binding platform 推导 user_id）。"""
    client, components = api
    post = await client.post("/api/conversations", json={
        "platform": "wechat", "account_id": "acc1",
        "contact_id": "wxid_test", "persona_id": "gf001",
    })
    conv_id = (await post.json())["conversation_id"]

    # 预先塞几条 chat_history（任意 user_id，验证 delete_user 被调用）
    components.chat_history.add_test_message("user", "hi")
    components.chat_history.add_test_message("assistant", "hello")

    resp = await client.delete(f"/api/conversations/{conv_id}")
    assert resp.status == 200

    # delete_user 应被调用，user_id 为 wechat::acc1::wxid_test
    expected_uid = "wechat::acc1::wxid_test"
    assert expected_uid in components.chat_history.deleted_users
    # messages 被清空
    assert components.chat_history.messages == []


async def test_api_delete_conversation_web_platform_uid(api):
    """DELETE web 平台对话 → user_id = web::{persona_id}。"""
    client, components = api
    post = await client.post("/api/conversations", json={
        "platform": "web", "account_id": "",
        "contact_id": "web_user", "persona_id": "gf001",
    })
    conv_id = (await post.json())["conversation_id"]

    resp = await client.delete(f"/api/conversations/{conv_id}")
    assert resp.status == 200
    assert "web::gf001" in components.chat_history.deleted_users


async def test_api_delete_conversation_not_found_404(api):
    """DELETE 不存在的 conversation → 404，且不调 chat_history.delete_user。"""
    client, components = api
    resp = await client.delete("/api/conversations/conv_999")
    assert resp.status == 404
    assert components.chat_history.deleted_users == []
