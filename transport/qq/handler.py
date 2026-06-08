"""QQ 消息处理器"""

import os

from loguru import logger

from ..base import BaseTransport, IncomingMessage, OutgoingMessage
from .napcat import NapCatClient


class QQTransport(BaseTransport):
    """QQ 传输层

    通过 NapCat (OneBot 11) 接入 QQ。
    支持正向 WebSocket 和 HTTP API 两种通信方式。
    """

    def __init__(
        self,
        ws_url: str = "ws://127.0.0.1:3001",
        http_url: str = "",
        access_token: str = "",
    ):
        self._client = NapCatClient(
            ws_url=ws_url,
            http_url=http_url,
            access_token=access_token,
        )
        self._message_handler = None

    @property
    def platform(self) -> str:
        return "qq"

    def set_message_handler(self, handler) -> None:
        """设置消息处理回调（接受 IncomingMessage，返回回复文本）"""
        self._message_handler = handler
        # 包装成 NapCat 的回调格式
        self._client.set_handler(self._wrap_handler)

    def _wrap_handler(self, user_id: str, content: str, raw_data: dict) -> "Awaitable[str]":
        """将 NapCat 回调包装为统一格式"""
        import asyncio

        msg = IncomingMessage(
            platform="qq",
            user_id=user_id,
            content=content,
            raw_data=raw_data,
        )

        if self._message_handler:
            return self._message_handler(msg)
        else:
            # 返回一个已完成的 Future
            future = asyncio.get_event_loop().create_future()
            future.set_result("我还没准备好聊天呢~")
            return future

    async def start(self) -> None:
        """启动 QQ 服务（WebSocket 连接）"""
        logger.info(f"QQ transport starting, connecting to {self._client._ws_url}")
        await self._client.connect_ws()

    async def stop(self) -> None:
        await self._client.close()
        logger.info("QQ transport stopped")

    async def send_message(self, user_id: str, message: OutgoingMessage) -> bool:
        return await self._client.send_private_msg(user_id, message.content)
