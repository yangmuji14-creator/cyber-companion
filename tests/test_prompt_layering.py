"""§9 fixed-prefix prompt layering regression tests.

Contract: across turns the stable system prefix (persona/role) is byte-identical
and only the dynamic tail (runtime state / time / fuse) changes. This keeps the
prompt prefix reusable/cachable and guarantees the literary Brain Diary never
leaks into the model prompt (only the structured runtime context is appended).

These tests exercise the pure functions insert_dynamic_context / trim_messages
so they are deterministic and network-free.
"""
from core.chat.context_builder import (
    insert_dynamic_context,
    trim_messages_to_budget,
)

STABLE_PREFIX = [
    {"role": "system", "content": "[PERSONA] 你是慕，温柔、细腻的伴侣。你的职责是自然、温柔地陪对方聊天。"},
    {"role": "system", "content": "[RULES] 先说对方在意的，再自然延伸；不查资料；语气像真人。"},
]


def _history(with_reply: bool, reply: str = "我也想你呀。") -> list[dict[str, str]]:
    msgs = [
        {"role": "system", "content": STABLE_PREFIX[0]["content"]},
        {"role": "system", "content": STABLE_PREFIX[1]["content"]},
        {"role": "user", "content": "今天好累啊", "sticker": {"x": 1}, "timestamp": "1"},
        {"role": "assistant", "content": "抱抱你，辛苦了。"},
        {"role": "user", "content": "你呢，今天怎么样", "timestamp": "2"},
    ]
    if with_reply:
        msgs.append({"role": "assistant", "content": reply, "timestamp": "3"})
    return msgs


# ── 9a: 动态上下文只改尾部，稳定 system 前缀字节不变 ──
def test_dynamic_context_injected_at_tail_keeps_prefix():
    base_history = _history(with_reply=False)

    ctx_a = "【运行状态】对方现在心情低落，需要安慰。"
    ctx_b = "【运行状态】对方现在很开心，可以聊轻松话题。"

    ra = insert_dynamic_context(base_history, ctx_a)
    rb = insert_dynamic_context(base_history, ctx_b)

    # 前缀两条 system 与原始完全一致
    assert ra[:2] == STABLE_PREFIX
    assert rb[:2] == STABLE_PREFIX

    # 动态 system 只插在最后一条 user 消息之前（尾部），且只差一条
    dyn_a = [i for i, m in enumerate(ra) if m["content"] == ctx_a]
    dyn_b = [i for i, m in enumerate(rb) if m["content"] == ctx_b]
    assert len(dyn_a) == 1 and len(dyn_b) == 1
    # 两条结果在动态注入点之外完全一致（前缀 + 对话历史逐一相同）
    for i, (ma, mb) in enumerate(zip(ra, rb)):
        if i != dyn_a[0] and i != dyn_b[0]:
            assert ma == mb
    # 稳定前缀跨轮次字节一致
    assert ra[:2] == rb[:2]


# ── 9b: 裁剪只作用于请求副本，保留 system 前缀 ──
def test_trim_messages_keeps_system_prefix():
    history = _history(with_reply=True)
    trimmed = trim_messages_to_budget(history, max_chars=10_000, reserved_chars=100)

    # 前两条 system 稳定前缀必须保留
    assert [m.get("content") for m in trimmed[:2]] == [
        s["content"] for s in STABLE_PREFIX
    ]
    # 裁剪后不包含 UI-only 元数据（sticker/timestamp/emotion）
    for m in trimmed:
        assert "sticker" not in m
        assert "timestamp" not in m


# ── 9c: 预算收缩会截断早期对话，但当前请求始终保留 ──
def test_trim_messages_always_keeps_current_user_request():
    history = _history(with_reply=True)
    tiny = trim_messages_to_budget(history, max_chars=1, reserved_chars=0)
    # 预算极小时只保当前 user 请求（系统前缀可被裁剪，但当前请求绝不丢失）
    assert any(m["role"] == "user" and m["content"] == "你呢，今天怎么样" for m in tiny)
    # 正常预算下 system 前缀保留在前（见 test_trim_messages_keeps_system_prefix）
    normal = trim_messages_to_budget(_history(with_reply=True), max_chars=10_000)
    assert normal[:2] == STABLE_PREFIX
