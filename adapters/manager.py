"""Adapter Manager — 适配器管理器

管理多个平台适配器的注册、启动、消息分发。

支持同平台多账号：_adapters 键为 `f"{platform}:{account_id}"`，默认 account_id="default"。
向后兼容：get(platform) 不传 account_id 时，若该平台仅 1 个适配器则返回它，>1 个则 raise ValueError。
"""

import threading
from typing import Any

from loguru import logger

from .base import BaseAdapter, AdapterMessage, AdapterConfig


def _key(platform: str, account_id: str) -> str:
    """构造 _adapters 字典键"""
    return f"{platform}:{account_id}"


class AdapterManager:
    """适配器管理器（多账号感知）"""

    def __init__(self):
        self._adapters: dict[str, BaseAdapter] = {}
        self._message_handler = None
        self._lock = threading.Lock()

    def register(self, adapter: BaseAdapter, account_id: str = "default") -> None:
        """注册适配器

        Args:
            adapter: 适配器实例
            account_id: 账号 ID，默认 "default"。重复 (platform, account_id) 会告警并替换。
        """
        platform = adapter.config.platform
        # 同步 account_id 到 adapter.config，保证 adapter.account_id 与注册键一致
        adapter.config.account_id = account_id
        k = _key(platform, account_id)
        with self._lock:
            if k in self._adapters:
                logger.warning(f"Adapter for '{k}' already registered, replacing")
            self._adapters[k] = adapter
            # 若已设全局 message_handler，立即注入到新 adapter
            # （避免 SSE 登录后新创建的 adapter 漏设 handler 导致消息静默丢弃）
            if self._message_handler is not None:
                adapter.set_handler(self._message_handler)
        logger.info(f"Registered adapter: {k}")

    def unregister(self, platform: str, account_id: str = "default") -> bool:
        """注销适配器"""
        k = _key(platform, account_id)
        with self._lock:
            if k in self._adapters:
                del self._adapters[k]
                logger.info(f"Unregistered adapter: {k}")
                return True
            return False

    def get(self, platform: str, account_id: str | None = None) -> BaseAdapter | None:
        """获取适配器

        Args:
            platform: 平台标识
            account_id: 账号 ID。None（默认）表示不指定：
                - 该平台 0 个适配器 → 返回 None
                - 该平台 1 个适配器 → 返回它（向后兼容）
                - 该平台 >1 个适配器 → raise ValueError

        Returns:
            适配器实例或 None
        """
        with self._lock:
            if account_id is not None:
                return self._adapters.get(_key(platform, account_id))
            # 向后兼容：未指定 account_id
            matches = [a for a in self._adapters.values() if a.config.platform == platform]
            if len(matches) == 0:
                return None
            if len(matches) == 1:
                return matches[0]
            raise ValueError(
                f"Multiple adapters for platform '{platform}', specify account_id"
            )

    def list_adapters(self) -> list[BaseAdapter]:
        """列出所有适配器（全平台全账号）"""
        with self._lock:
            return list(self._adapters.values())

    def list_enabled(self) -> list[BaseAdapter]:
        """列出所有启用的适配器"""
        with self._lock:
            return [a for a in self._adapters.values() if a.config.enabled]

    def list_by_platform(self, platform: str) -> list[BaseAdapter]:
        """列出某平台所有账号的适配器"""
        with self._lock:
            return [a for a in self._adapters.values() if a.config.platform == platform]

    def list_accounts(self, platform: str) -> list[str]:
        """返回某平台所有已注册的 account_id"""
        with self._lock:
            return [
                a.config.account_id
                for a in self._adapters.values()
                if a.config.platform == platform
            ]

    def set_message_handler(self, handler) -> None:
        """设置全局消息处理回调

        所有适配器收到的消息都会通过这个回调处理。
        """
        with self._lock:
            self._message_handler = handler
            for adapter in self._adapters.values():
                adapter.set_handler(handler)

    async def start_all(self) -> None:
        """启动所有启用的适配器"""
        for adapter in self.list_enabled():
            try:
                await adapter.start()
                logger.info(f"Started adapter: {adapter.config.platform}:{adapter.account_id}")
            except Exception as e:
                logger.error(
                    f"Failed to start adapter {adapter.config.platform}:{adapter.account_id}: {e}"
                )

    async def stop_all(self) -> None:
        """停止所有适配器"""
        for adapter in self.list_adapters():
            try:
                await adapter.stop()
                logger.info(f"Stopped adapter: {adapter.config.platform}:{adapter.account_id}")
            except Exception as e:
                logger.error(
                    f"Failed to stop adapter {adapter.config.platform}:{adapter.account_id}: {e}"
                )

    async def send_to_platform(
        self, platform: str, account_id: str, user_id: str, content: str, **kwargs
    ) -> bool:
        """向指定平台的指定账号发送消息

        Args:
            platform: 平台标识
            account_id: 账号 ID（必填）
            user_id: 用户 ID
            content: 消息内容
        """
        adapter = self.get(platform, account_id)
        if not adapter:
            logger.warning(f"Adapter for '{platform}:{account_id}' not found")
            return False
        return await adapter.send(user_id, content, **kwargs)

    async def broadcast(
        self, content: str, platforms: list[str] | None = None, **kwargs
    ) -> dict[str, bool]:
        """广播消息到多个平台

        Args:
            content: 消息内容
            platforms: 目标平台列表，None 表示所有启用的平台（所有账号）

        Returns:
            {f"{platform}:{account_id}": success}
        """
        with self._lock:
            enabled = [a for a in self._adapters.values() if a.config.enabled]
        if platforms:
            enabled = [a for a in enabled if a.config.platform in platforms]
        results: dict[str, bool] = {}
        for adapter in enabled:
            k = _key(adapter.config.platform, adapter.account_id)
            try:
                results[k] = await adapter.send("", content, **kwargs)
            except Exception as e:
                logger.error(f"Broadcast to {k} failed: {e}")
                results[k] = False
        return results

    def get_info(self) -> list[dict[str, Any]]:
        """获取所有适配器信息"""
        return [a.get_info() for a in self.list_adapters()]
