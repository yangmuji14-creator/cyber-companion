import asyncio

import pytest

from core.runtime import BackgroundTaskManager


@pytest.mark.asyncio
async def test_task_manager_tracks_completed_work():
    manager = BackgroundTaskManager()
    completed = []

    async def work():
        completed.append(True)

    manager.create(work(), name="test-work")
    await asyncio.sleep(0)
    assert completed == [True]
    await asyncio.sleep(0)
    assert manager.active_count == 0


@pytest.mark.asyncio
async def test_task_manager_bounds_and_shuts_down_work():
    manager = BackgroundTaskManager(max_tasks=1)
    started = asyncio.Event()

    async def slow_work():
        started.set()
        await asyncio.Event().wait()

    async def skipped_work():
        return None

    assert manager.create(slow_work()) is not None
    await started.wait()
    assert manager.create(skipped_work()) is None
    await manager.shutdown()
    assert manager.active_count == 0
