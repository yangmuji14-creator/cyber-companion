"""ilink API 客户端 - 与 ilink-wechat 通信"""

import aiohttp
from loguru import logger


class ILinkClient:
    """ilink API 客户端

    负责与 ilink-wechat 服务通信，发送消息到微信。
    ilink-wechat 作为中间层，接收我们的回复并转发给微信用户。
    """

    def __init__(self, endpoint: str, auth_token: str = ""):
        """
        Args:
            endpoint: ilink-wechat 的消息接收端点，如 http://localhost:3000/api/bot/ilink
            auth_token: 认证令牌
        """
        self._endpoint = endpoint.rstrip("/")
        self._auth_token = auth_token
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def send_reply(
        self,
        text: str,
        context_token: str = "",
        media_url: str = "",
    ) -> bool:
        """通过 ilink 发送回复消息

        Args:
            text: 回复文本
            context_token: ilink 传来的上下文令牌（必须原样回传）
            media_url: 媒体 URL（图片/音频）

        Returns:
            是否发送成功
        """
        session = await self._get_session()

        payload: dict = {}
        if text:
            payload["text"] = text
        if media_url:
            payload["mediaUrl"] = media_url

        headers = {"Content-Type": "application/json"}
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"

        try:
            async with session.post(
                self._endpoint,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    logger.debug(f"ilink reply sent: {text[:30]}...")
                    return True
                else:
                    body = await resp.text()
                    logger.error(f"ilink reply failed [{resp.status}]: {body}")
                    return False
        except Exception as e:
            logger.error(f"ilink reply error: {e}")
            return False
