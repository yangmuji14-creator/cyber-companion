"""Adapter Base — 适配器基类

所有平台适配器必须继承 BaseAdapter 并实现必要方法。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

from loguru import logger


@dataclass
class AdapterConfig:
    """适配器配置"""
    platform: str           # 平台标识：cli, webui, wechat, qq, telegram, discord, api
    enabled: bool = True
    token: str = ""         # 平台 token（如需要）
    webhook_url: str = ""   # Webhook URL（如需要）
    settings: dict[str, Any] = field(default_factory=dict)  # 平台特定设置


@dataclass
class AdapterMessage:
    """适配器消息格式"""
    user_id: str            # 用户 ID
    content: str            # 消息内容
    message_id: str = ""    # 消息 ID（用于回复）
    platform: str = ""      # 来源平台
    timestamp: str = ""     # 时间戳
    metadata: dict[str, Any] = field(default_factory=dict)  # 平台特定数据


# 消息处理回调类型
MessageHandler = Callable[[AdapterMessage], Awaitable[str]]


class BaseAdapter(ABC):
    """适配器基类"""

    def __init__(self, config: AdapterConfig):
        self.config = config
        self._handler: MessageHandler | None = None
        self._logger = logger.bind(platform=config.platform)

    def set_handler(self, handler: MessageHandler) -> None:
        """设置消息处理回调"""
        self._handler = handler

    @abstractmethod
    async def start(self) -> None:
        """启动适配器"""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """停止适配器"""
        pass

    @abstractmethod
    async def send(self, user_id: str, content: str, **kwargs) -> bool:
        """发送消息给用户

        Args:
            user_id: 用户 ID
            content: 消息内容

        Returns:
            是否发送成功
        """
        pass

    @abstractmethod
    async def reply(self, message: AdapterMessage, content: str, **kwargs) -> bool:
        """回复消息

        Args:
            message: 原始消息
            content: 回复内容

        Returns:
            是否回复成功
        """
        pass

    async def on_message(self, message: AdapterMessage) -> str:
        """处理收到的消息

        默认实现：调用注册的 handler
        """
        if self._handler:
            return await self._handler(message)
        return ""

    def get_info(self) -> dict[str, Any]:
        """获取适配器信息"""
        return {
            "platform": self.config.platform,
            "enabled": self.config.enabled,
        }
