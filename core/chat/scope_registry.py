"""ScopeExecutionRegistry — per-scope serialization and request idempotency.

Implements plan S6.2 / S6.3 for the ChatPipeline layer:

- **Per-scope serialization**: all work for the *same* memory scope (normal
  messages, /regen, memory extraction, proactive messages, uploads) runs
  through one asyncio.Lock, so messages from one conversation cannot land
  out of order or interleave half-written turns. Different scopes never block
  each other, so multi-conversation / multi-account load stays parallel.

- **Cancel safety**: asyncio.Lock.acquire() is itself cancellation-aware —
  a task cancelled while waiting is removed from the lock's wait queue, so a
  disconnected client is never stuck forever behind a busy scope.

- **Request idempotency**: a (scope_id, request_id) submission that is already
  in flight, or already completed, is deduplicated — retrying the same
  request_id does not call the model a second time and returns the recorded
  result. Idempotency is a best-effort dedup of *final results*; token-wise
  streaming is delivered only to the first client.

- **TTL pruning**: idle locks are reference counted and evicted after
  idle_ttl seconds so the registry cannot grow without bound.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


class ScopeExecutionRegistry:
    """Serializes generation per scope and dedups requests per (scope, request_id)."""

    def __init__(self, idle_ttl: float = 300.0, max_results: int = 20000) -> None:
        self._idle_ttl = idle_ttl
        self._max_results = max_results
        self._locks: dict[str, asyncio.Lock] = {}
        self._refcount: dict[str, int] = {}
        self._last_used: dict[str, float] = {}
        # (scope_id, request_id) -> in-flight task or completed result marker.
        self._inflight: dict[tuple[str, str], asyncio.Task] = {}
        self._results: OrderedDict[tuple[str, str], Any] = OrderedDict()

    # introspection
    def active_scopes(self) -> int:
        return len(self._locks)

    def refcount(self, scope_id: str) -> int:
        return self._refcount.get(scope_id, 0)

    def is_busy(self, scope_id: str) -> bool:
        lock = self._locks.get(scope_id)
        return bool(lock is not None and lock.locked())

    # internal helpers
    def _lock_for(self, scope_id: str) -> asyncio.Lock:
        lock = self._locks.get(scope_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[scope_id] = lock
            self._refcount[scope_id] = 0
            self._last_used[scope_id] = time.monotonic()
            if len(self._locks) > 128:
                self._prune()
        return lock

    def _prune(self) -> None:
        now = time.monotonic()
        for scope_id in list(self._locks.keys()):
            if (
                self._refcount.get(scope_id, 0) == 0
                and self._locks[scope_id].locked() is False
                and (now - self._last_used.get(scope_id, 0.0)) > self._idle_ttl
            ):
                self._locks.pop(scope_id, None)
                self._refcount.pop(scope_id, None)
                self._last_used.pop(scope_id, None)

    def cleanup(self) -> int:
        before = len(self._locks)
        self._prune()
        return before - len(self._locks)

    @asynccontextmanager
    async def run_exclusive(self, scope_id: str, *, wait: bool = True):
        """Serialize one unit of work for scope_id."""
        if not scope_id:
            yield
            return

        lock = self._lock_for(scope_id)
        self._refcount[scope_id] += 1
        try:
            if wait:
                await lock.acquire()
            elif lock.locked():
                raise RuntimeError(f"scope {scope_id!r} is busy")
            self._last_used[scope_id] = time.monotonic()
            try:
                yield
            finally:
                try:
                    lock.release()
                except RuntimeError:
                    pass
        finally:
            self._refcount[scope_id] -= 1
            if self._refcount[scope_id] <= 0:
                self._last_used[scope_id] = time.monotonic()

    async def submit(
        self,
        scope_id: str,
        request_id: str,
        coro_fn: Callable[[], Awaitable[Any]],
        *,
        dedup: bool = True,
    ) -> Any:
        """Serialize coro_fn per scope; dedup repeated (scope, request_id)."""
        if not scope_id:
            return await coro_fn()

        if dedup and request_id:
            key = (scope_id, request_id)
            inflight = self._inflight.get(key)
            if inflight is not None:
                return await inflight
            if key in self._results:
                return self._results[key]

        async def _run():
            async with self.run_exclusive(scope_id):
                return await coro_fn()

        if dedup and request_id:
            key = (scope_id, request_id)
            task = asyncio.create_task(_run())
            self._inflight[key] = task
            try:
                result = await task
            except asyncio.CancelledError:
                if self._inflight.get(key) is task:
                    self._inflight.pop(key, None)
                    self._results.pop(key, None)
                raise
            except BaseException:
                self._inflight.pop(key, None)
                self._results.pop(key, None)
                raise
            else:
                self._inflight.pop(key, None)
                self._results[key] = result
                self._results.move_to_end(key)
                while len(self._results) > self._max_results:
                    self._results.popitem(last=False)
                return result

        return await _run()

    def drop_request(self, scope_id: str, request_id: str) -> None:
        key = (scope_id, request_id)
        self._inflight.pop(key, None)
        self._results.pop(key, None)


def supports_scope_id(pipeline: Any) -> bool:
    try:
        return "scope_id" in inspect.signature(pipeline.process).parameters
    except (TypeError, ValueError):
        return False
