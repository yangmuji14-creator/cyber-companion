"""DebounceManager — 消息去抖模块

多平台消息去抖：按平台 + 用户隔离，自动合并短时间内的连续消息后再处理。
"""

import asyncio
import re
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from core.app import AppComponents
    from core.chat.pipeline import ChatPipeline
    from adapters.manager import AdapterManager


class DebounceState:
    """消息去抖状态（按平台 + 用户隔离）"""

    def __init__(self, platform: str, user_id: str, timeout: float,
                 pipeline: "ChatPipeline", app: "AppComponents", manager: "AdapterManager"):
        self.platform = platform
        self.user_id = user_id
        self.timeout = timeout
        self.pipeline = pipeline
        self.app = app
        self.manager = manager
        self.queue: list[str] = []
        self._timer_task: asyncio.Task | None = None

    async def add(self, text: str) -> None:
        """添加消息到去抖队列"""
        self.queue.append(text)
        await self._reset_timer()

    async def _reset_timer(self) -> None:
        if self._timer_task:
            self._timer_task.cancel()
        self._timer_task = asyncio.create_task(self._debounce_timer())

    async def _debounce_timer(self) -> None:
        try:
            await asyncio.sleep(self.timeout)
            await self.flush()
        except asyncio.CancelledError:
            pass

    async def flush(self) -> None:
        """立即处理队列中所有消息，并按空行分段发送"""
        if not self.queue:
            return
        combined = "\n".join(self.queue)
        self.queue = []
        self._timer_task = None
        try:
            from core.config import DEFAULT_PERSONA_ID
            reply, _ = await self.pipeline.process(
                self.user_id, combined, DEFAULT_PERSONA_ID,
            )
            adapter = self.manager.get(self.platform)
            if adapter:
                _send_segments(adapter, self.user_id, reply)
        except Exception as e:
            logger.error(f"Debounce flush error ({self.platform}/{self.user_id}): {e}")


def _send_segments(adapter, user_id: str, reply: str) -> None:
    """将回复分段发送，自动控制总段数不超过6段"""
    raw = re.split(r'(。|！|？|，|\n|\.|\!|\?|,)', reply)
    sentences = []
    i = 0
    while i < len(raw):
        if i + 1 < len(raw):
            delim = raw[i + 1]
            if delim in ("，", ","):
                sentence = raw[i].strip()
            else:
                sentence = (raw[i] + delim).strip()
            i += 2
        else:
            sentence = raw[i].strip()
            i += 1
        if sentence:
            sentences.append(sentence)

    group_size = max(1, (len(sentences) + 5) // 6)
    segments = []
    for j in range(0, len(sentences), group_size):
        segment = "".join(sentences[j:j + group_size])
        if segment.strip():
            segments.append(segment.strip())

    if not segments:
        segments = [reply]

    async def _send():
        for idx, seg in enumerate(segments):
            await adapter.send(user_id, seg)
            if idx < len(segments) - 1:
                await asyncio.sleep(0.8)

    asyncio.create_task(_send())


class DebounceManager:
    """统一消息去抖管理器"""

    def __init__(self, timeout: float, pipeline, app, manager):
        self.timeout = timeout
        self.pipeline = pipeline
        self.app = app
        self.manager = manager
        self._states: dict[str, DebounceState] = {}

    def _key(self, platform: str, user_id: str) -> str:
        return f"{platform}:{user_id}"

    async def add_message(self, platform: str, user_id: str, text: str) -> None:
        """添加消息到去抖队列"""
        key = self._key(platform, user_id)
        if key not in self._states:
            self._states[key] = DebounceState(
                platform, user_id, self.timeout,
                self.pipeline, self.app, self.manager,
            )
        await self._states[key].add(text)

    async def flush_all(self) -> None:
        """立即刷新所有队列"""
        for state in self._states.values():
            await state.flush()
