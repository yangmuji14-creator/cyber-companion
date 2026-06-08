"""传输层统一接口"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class IncomingMessage:
    """收到的消息"""

    platform: str  # wechat / qq / telegram
    user_id: str
    content: str
    message_type: str = "text"  # text / image / voice
    raw_data: dict[str, Any] = field(default_factory=dict)
    # 用于回复的上下文信息
    reply_context: dict[str, Any] = field(default_factory=dict)


@dataclass
class OutgoingMessage:
    """要发送的消息"""

    content: str
    message_type: str = "text"
    media_url: str | None = None


class BaseTransport(ABC):
    """传输层基类"""

    @property
    @abstractmethod
    def platform(self) -> str:
        """平台名称"""
        ...

    @abstractmethod
    async def start(self) -> None:
        """启动服务"""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """停止服务"""
        ...

    @abstractmethod
    async def send_message(self, user_id: str, message: OutgoingMessage) -> bool:
        """发送消息"""
        ...
