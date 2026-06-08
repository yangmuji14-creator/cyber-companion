"""微信消息处理器 - 接收 ilink 回调并处理"""

from typing import Any, Callable, Awaitable

from loguru import logger

from ..base import IncomingMessage, OutgoingMessage, BaseTransport
from .api import ILinkClient


# 消息处理回调类型：接收 IncomingMessage，返回回复文本
MessageHandler = Callable[[IncomingMessage], Awaitable[str]]


class WeChatTransport(BaseTransport):
    """微信传输层

    通过 ilink-wechat 接收和发送微信消息。
    架构：微信用户 ↔ ilink-wechat (Node.js) ↔ 我们的 FastAPI 端点
    """

    def __init__(
        self,
        ilink_endpoint: str,
        auth_token: str = "",
        callback_auth_token: str = "",
    ):
        self._client = ILinkClient(
            endpoint=ilink_endpoint,
            auth_token=auth_token,
        )
        self._callback_auth_token = callback_auth_token
        self._handler: MessageHandler | None = None

    @property
    def platform(self) -> str:
        return "wechat"

    def set_handler(self, handler: MessageHandler) -> None:
        """设置消息处理回调"""
        self._handler = handler

    async def start(self) -> None:
        logger.info("WeChat transport started (via ilink)")

    async def stop(self) -> None:
        await self._client.close()
        logger.info("WeChat transport stopped")

    async def handle_webhook(self, data: dict[str, Any]) -> dict[str, str]:
        """处理 ilink-wechat 发来的 webhook 请求

        ilink POST 格式：
        {
            "from": "用户ID",
            "body": "消息内容",
            "contextToken": "上下文令牌",
            "accountId": "账号ID",
            "mediaPath": "可选",
            "mediaType": "可选"
        }

        Returns:
            {"text": "回复内容"} 格式的响应
        """
        user_id = data.get("from", "unknown")
        body = data.get("body", "")
        context_token = data.get("contextToken", "")
        account_id = data.get("accountId", "")
        media_path = data.get("mediaPath", "")
        media_type = data.get("mediaType", "")

        logger.info(f"[WeChat] 收到消息 from={user_id}: {body[:50]}...")

        # 构建统一消息对象
        msg = IncomingMessage(
            platform="wechat",
            user_id=user_id,
            content=body,
            message_type="text",
            raw_data=data,
            reply_context={"contextToken": context_token, "accountId": account_id},
        )

        # 如果有媒体
        if media_path:
            msg.message_type = "image" if "image" in media_type else "voice"

        # 调用处理回调
        if self._handler:
            try:
                reply_text = await self._handler(msg)
                return {"text": reply_text}
            except Exception as e:
                logger.error(f"Handler error: {e}")
                return {"text": "抱歉，处理消息时出了点问题 (´;ω;`)"}
        else:
            logger.warning("No handler set for WeChat transport")
            return {"text": "我还没准备好聊天呢~"}

    async def send_message(self, user_id: str, message: OutgoingMessage) -> bool:
        """主动发送消息（非回复场景）"""
        return await self._client.send_reply(
            text=message.content,
            media_url=message.media_url or "",
        )
