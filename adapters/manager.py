"""Adapter Manager — 适配器管理器

管理多个平台适配器的注册、启动、消息分发。
"""

from typing import Any

from loguru import logger

from .base import BaseAdapter, AdapterMessage, AdapterConfig


class AdapterManager:
    """适配器管理器"""

    def __init__(self):
        self._adapters: dict[str, BaseAdapter] = {}
        self._message_handler = None

    def register(self, adapter: BaseAdapter) -> None:
        """注册适配器"""
        platform = adapter.config.platform
        if platform in self._adapters:
            logger.warning(f"Adapter for '{platform}' already registered, replacing")

        self._adapters[platform] = adapter
        logger.info(f"Registered adapter: {platform}")

    def unregister(self, platform: str) -> bool:
        """注销适配器"""
        if platform in self._adapters:
            del self._adapters[platform]
            logger.info(f"Unregistered adapter: {platform}")
            return True
        return False

    def get(self, platform: str) -> BaseAdapter | None:
        """获取适配器"""
        return self._adapters.get(platform)

    def list_adapters(self) -> list[BaseAdapter]:
        """列出所有适配器"""
        return list(self._adapters.values())

    def list_enabled(self) -> list[BaseAdapter]:
        """列出所有启用的适配器"""
        return [a for a in self._adapters.values() if a.config.enabled]

    def set_message_handler(self, handler) -> None:
        """设置全局消息处理回调

        所有适配器收到的消息都会通过这个回调处理。
        """
        self._message_handler = handler
        # 同时设置到所有已注册的适配器
        for adapter in self._adapters.values():
            adapter.set_handler(handler)

    async def start_all(self) -> None:
        """启动所有启用的适配器"""
        for adapter in self.list_enabled():
            try:
                await adapter.start()
                logger.info(f"Started adapter: {adapter.config.platform}")
            except Exception as e:
                logger.error(f"Failed to start adapter {adapter.config.platform}: {e}")

    async def stop_all(self) -> None:
        """停止所有适配器"""
        for adapter in self.list_adapters():
            try:
                await adapter.stop()
                logger.info(f"Stopped adapter: {adapter.config.platform}")
            except Exception as e:
                logger.error(f"Failed to stop adapter {adapter.config.platform}: {e}")

    async def send_to_platform(self, platform: str, user_id: str, content: str, **kwargs) -> bool:
        """向指定平台发送消息"""
        adapter = self.get(platform)
        if not adapter:
            logger.warning(f"Adapter for '{platform}' not found")
            return False
        return await adapter.send(user_id, content, **kwargs)

    async def broadcast(self, content: str, platforms: list[str] | None = None, **kwargs) -> dict[str, bool]:
        """广播消息到多个平台

        Args:
            content: 消息内容
            platforms: 目标平台列表，None 表示所有启用的平台

        Returns:
            {platform: success}
        """
        targets = platforms or [a.config.platform for a in self.list_enabled()]
        results = {}

        for platform in targets:
            adapter = self.get(platform)
            if adapter and adapter.config.enabled:
                results[platform] = await adapter.send("", content, **kwargs)
            else:
                results[platform] = False

        return results

    def get_info(self) -> list[dict[str, Any]]:
        """获取所有适配器信息"""
        return [a.get_info() for a in self.list_adapters()]
