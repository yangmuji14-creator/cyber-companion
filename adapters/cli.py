"""CLI Adapter — 命令行适配器

将现有的 CLI 聊天转换为适配器模式。
"""

import asyncio
import queue
import threading
from datetime import datetime

from loguru import logger

from .base import BaseAdapter, AdapterMessage, AdapterConfig


class CLIAdapter(BaseAdapter):
    """命令行适配器"""

    def __init__(self, config: AdapterConfig | None = None):
        if config is None:
            config = AdapterConfig(platform="cli")
        super().__init__(config)

        self._input_queue: queue.Queue[str | None] = queue.Queue()
        self._running = False
        self._thread: threading.Thread | None = None

    async def start(self) -> None:
        """启动 CLI 适配器"""
        self._running = True
        self._thread = threading.Thread(target=self._input_reader, daemon=True)
        self._thread.start()
        logger.info("CLI adapter started")

    async def stop(self) -> None:
        """停止 CLI 适配器"""
        self._running = False
        self._input_queue.put(None)
        if self._thread:
            self._thread.join(timeout=2)
        logger.info("CLI adapter stopped")

    def _input_reader(self):
        """输入读取线程"""
        while self._running:
            try:
                line = input("你: ").strip()
                if line:
                    self._input_queue.put(line)
            except (EOFError, KeyboardInterrupt):
                self._input_queue.put(None)
                break

    async def get_input(self, timeout: float = 1.0) -> str | None:
        """获取用户输入（非阻塞）"""
        try:
            return await asyncio.get_event_loop().run_in_executor(
                None, lambda: self._input_queue.get(timeout=timeout)
            )
        except queue.Empty:
            return None

    async def send(self, user_id: str, content: str, **kwargs) -> bool:
        """发送消息到终端"""
        print(f"\nAI: {content}")
        return True

    async def reply(self, message: AdapterMessage, content: str, **kwargs) -> bool:
        """回复消息"""
        return await self.send(message.user_id, content, **kwargs)

    def create_message(self, user_id: str, content: str) -> AdapterMessage:
        """创建 CLI 消息"""
        return AdapterMessage(
            user_id=user_id,
            content=content,
            platform="cli",
            timestamp=datetime.now().isoformat(),
        )
