"""Bounded lifecycle management for fire-and-forget asyncio work."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

from loguru import logger


class BackgroundTaskManager:
    """Track background work, cap concurrency, and provide graceful shutdown."""

    def __init__(self, max_tasks: int = 32) -> None:
        self._max_tasks = max_tasks
        self._tasks: set[asyncio.Task[Any]] = set()
        self._closing = False

    @property
    def active_count(self) -> int:
        return len(self._tasks)

    def create(self, coro: Coroutine[Any, Any, Any], *, name: str = "background") -> asyncio.Task[Any] | None:
        if self._closing:
            coro.close()
            return None
        if len(self._tasks) >= self._max_tasks:
            coro.close()
            logger.warning(f"Background task limit reached ({self._max_tasks}); skipped {name}")
            return None
        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._finish)
        return task

    def _finish(self, task: asyncio.Task[Any]) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        try:
            exc = task.exception()
        except asyncio.CancelledError:
            return
        if exc is not None:
            logger.debug(f"Background task failed: {exc}")

    async def shutdown(self) -> None:
        self._closing = True
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
