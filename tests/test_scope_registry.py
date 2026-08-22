"""Tests for core/chat/scope_registry.py — per-scope serialization, cancellation
and request idempotency (plan S6.2 / S6.3).

asyncio_mode=auto so async tests need no marker.
"""

import asyncio
import time

import pytest

from core.chat.scope_registry import ScopeExecutionRegistry


@pytest.fixture
def registry():
    return ScopeExecutionRegistry(idle_ttl=0.05)


async def _append_and_sleep(shared, value, delay=0.01):
    """Append a start marker, sleep, then append an end marker."""
    shared.append(("start", value))
    await asyncio.sleep(delay)
    shared.append(("end", value))
    return value


# ── S6.2: same-scope serialization / different-scope parallelism ──

async def test_same_scope_runs_serially_in_order(registry):
    """10 concurrent submissions on one scope land start/end strictly in order."""
    shared = []

    async def work(i):
        shared.append(i)

    await asyncio.gather(*[
        registry.submit("scope_a", f"req-{i}", lambda i=i: work(i), dedup=False)
        for i in range(10)
    ])
    assert shared == list(range(10))


async def test_different_scopes_run_concurrently(registry):
    """N scopes with a 0.2s sleep should finish in parallel, not 0.2*N serial."""
    n = 4
    started = time.monotonic()

    async def work():
        await asyncio.sleep(0.2)
        return True

    await asyncio.gather(*[
        registry.submit(f"scope-{i}", f"req-{i}", work, dedup=False)
        for i in range(n)
    ])
    elapsed = time.monotonic() - started
    # Parallel: ~0.2s. Serial would be ~0.8s. Allow generous margin.
    assert elapsed < 0.6


async def test_same_scope_not_reentrant(registry):
    """A second submit on a busy scope must wait for the first to finish."""
    order = []
    release = asyncio.Event()

    async def first():
        order.append("first-start")
        await release.wait()
        order.append("first-end")
        return "first"

    async def second():
        order.append("second-start")
        order.append("second-end")
        return "second"

    t1 = asyncio.create_task(registry.submit("s", "r1", first, dedup=False))
    await asyncio.sleep(0.02)
    t2 = asyncio.create_task(registry.submit("s", "r2", second, dedup=False))
    await asyncio.sleep(0.02)
    assert order == ["first-start"]  # second blocked behind the lock
    release.set()
    results = await asyncio.gather(t1, t2)
    assert results == ["first", "second"]
    assert order == ["first-start", "first-end", "second-start", "second-end"]


# ── S6.2: cancellation while waiting ──

async def test_cancel_while_waiting_releases_cleanly(registry):
    """A task cancelled while waiting for a busy scope must not remain queued."""
    release = asyncio.Event()
    hit = []

    async def first():
        hit.append("first")
        await release.wait()
        return "first"

    async def waiter():
        hit.append("waiting")
        return "waiter"

    t1 = asyncio.create_task(registry.submit("s", "r1", first, dedup=False))
    await asyncio.sleep(0.02)
    t2 = asyncio.create_task(registry.submit("s", "r2", waiter, dedup=False))
    await asyncio.sleep(0.02)
    # Cancel the waiter while it sits behind the lock.
    t2.cancel()
    with pytest.raises(asyncio.CancelledError):
        await t2
    # Release the first; a new submission for the same scope must proceed
    # (proving the cancelled waiter did not remain queued behind the lock).
    release.set()
    await t1
    assert await registry.submit("s", "r3", lambda: _append_and_sleep([], "x", 0), dedup=False) == "x"
    assert hit == ["first"]


# ── S6.3: request idempotency ──

async def test_idempotent_duplicate_reuses_completed_result(registry):
    calls = []

    async def work():
        calls.append("call")
        await asyncio.sleep(0.01)
        return "result"

    r1 = await registry.submit("scope_a", "req-x", work, dedup=True)
    r2 = await registry.submit("scope_a", "req-x", work, dedup=True)
    assert r1 == r2 == "result"
    assert calls == ["call"]  # model called exactly once


async def test_idempotent_concurrent_duplicate_awaits_same(registry):
    calls = []

    async def work():
        calls.append("call")
        await asyncio.sleep(0.05)
        return "done"

    t1 = asyncio.create_task(registry.submit("scope_a", "req-x", work, dedup=True))
    await asyncio.sleep(0.01)  # let t1 start
    t2 = asyncio.create_task(registry.submit("scope_a", "req-x", work, dedup=True))
    r1, r2 = await asyncio.gather(t1, t2)
    assert r1 == r2 == "done"
    assert calls == ["call"]


async def test_distinct_request_ids_both_run(registry):
    calls = []

    async def work():
        calls.append(1)
        return "ok"

    await registry.submit("scope_a", "req-1", work, dedup=True)
    await registry.submit("scope_a", "req-2", work, dedup=True)
    assert calls == [1, 1]


# ── TTL pruning ──

async def test_idle_scope_is_pruned(registry):
    async def _noop():
        return None

    await registry.submit("ephemeral", "req-1", _noop, dedup=False)
    assert "ephemeral" in registry._locks
    await asyncio.sleep(0.08)  # longer than idle_ttl
    removed = registry.cleanup()
    assert removed >= 1
    assert "ephemeral" not in registry._locks


async def test_active_scope_not_pruned():
    reg = ScopeExecutionRegistry(idle_ttl=0.05)
    release = asyncio.Event()

    async def hold():
        await release.wait()

    t = asyncio.create_task(reg.submit("busy", "r1", hold, dedup=False))
    await asyncio.sleep(0.02)
    await asyncio.sleep(0.08)  # exceeds ttl but lock is held
    assert "busy" in reg._locks
    release.set()
    await t
