"""NapCat (OneBot 11) 客户端 - QQ 机器人接入"""

import json
import asyncio
from typing import Any, Callable, Awaitable

import aiohttp
from loguru import logger


# 消息处理回调
MessageHandler = Callable[[str, str, dict], Awaitable[str]]


class NapCatClient:
    """NapCat OneBot 11 客户端

    NapCat 是基于 QQNT 的 QQ 机器人框架，实现 OneBot 11 协议。
    支持正向 WebSocket 和 HTTP API 两种通信方式。

    文档: https://napneko.github.io/
    """

    def __init__(
        self,
        ws_url: str = "ws://127.0.0.1:3001",
        http_url: str = "",
        access_token: str = "",
    ):
        """
        Args:
            ws_url: NapCat 正向 WebSocket 地址
            http_url: NapCat HTTP API 地址（如果用 HTTP 模式）
            access_token: 访问令牌
        """
        self._ws_url = ws_url
        self._http_url = http_url.rstrip("/") if http_url else ""
        self._access_token = access_token
        self._session: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._handler: MessageHandler | None = None
        self._running = False
        self._self_id: str = ""

    def set_handler(self, handler: MessageHandler) -> None:
        """设置消息处理回调"""
        self._handler = handler

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers = {}
            if self._access_token:
                headers["Authorization"] = f"Bearer {self._access_token}"
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    async def close(self) -> None:
        """关闭连接"""
        self._running = False
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._session and not self._session.closed:
            await self._session.close()
        logger.info("NapCat client closed")

    # ========== WebSocket 模式 ==========

    async def connect_ws(self) -> None:
        """通过正向 WebSocket 连接 NapCat"""
        session = await self._get_session()

        try:
            self._ws = await session.ws_connect(self._ws_url)
            self._running = True
            logger.info(f"Connected to NapCat WebSocket: {self._ws_url}")

            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self._handle_ws_message(msg.data)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {self._ws.exception()}")
                    break
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING):
                    break

        except Exception as e:
            logger.error(f"NapCat WebSocket error: {e}")
        finally:
            self._running = False
            logger.info("NapCat WebSocket disconnected")

    async def _handle_ws_message(self, raw: str) -> None:
        """处理 WebSocket 收到的消息"""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return

        post_type = data.get("post_type")

        # 只处理消息事件
        if post_type != "message":
            return

        message_type = data.get("message_type")
        if message_type != "private":
            # 暂时只处理私聊，群聊后面再加
            return

        user_id = str(data.get("user_id", ""))
        raw_message = data.get("raw_message", "")
        message_id = data.get("message_id", 0)
        sender = data.get("sender", {})

        if not user_id or not raw_message:
            return

        self._self_id = str(data.get("self_id", ""))
        logger.info(f"[QQ] 收到消息 from={user_id}: {raw_message[:50]}...")

        if self._handler:
            try:
                reply_text = await self._handler(user_id, raw_message, data)
                if reply_text:
                    await self.send_private_msg(user_id, reply_text)
            except Exception as e:
                logger.error(f"Handler error: {e}")
                await self.send_private_msg(user_id, "抱歉，处理消息时出了点问题 (´;ω;`)")

    # ========== HTTP API ==========

    async def send_private_msg(self, user_id: str, message: str) -> bool:
        """发送私聊消息"""
        return await self._call_api("send_private_msg", {
            "user_id": int(user_id),
            "message": message,
        })

    async def send_group_msg(self, group_id: str, message: str) -> bool:
        """发送群消息"""
        return await self._call_api("send_group_msg", {
            "group_id": int(group_id),
            "message": message,
        })

    async def get_login_info(self) -> dict | None:
        """获取登录信息"""
        return await self._call_api("get_login_info", raw=True)

    async def _call_api(self, action: str, params: dict | None = None, raw: bool = False) -> Any:
        """调用 OneBot 11 API"""
        # 优先用 HTTP，如果没有 HTTP 地址则通过 WebSocket 发送
        if self._http_url:
            return await self._call_http_api(action, params, raw)
        elif self._ws and not self._ws.closed:
            return await self._call_ws_api(action, params, raw)
        else:
            logger.error("No connection available for API call")
            return None if raw else False

    async def _call_http_api(self, action: str, params: dict | None = None, raw: bool = False) -> Any:
        """通过 HTTP 调用 API"""
        session = await self._get_session()
        url = f"{self._http_url}/{action}"

        try:
            async with session.post(url, json=params or {}) as resp:
                data = await resp.json()
                if data.get("retcode") == 0:
                    return data.get("data") if raw else True
                else:
                    logger.error(f"API {action} failed: {data.get('msg')}")
                    return None if raw else False
        except Exception as e:
            logger.error(f"HTTP API {action} error: {e}")
            return None if raw else False

    async def _call_ws_api(self, action: str, params: dict | None = None, raw: bool = False) -> Any:
        """通过 WebSocket 调用 API"""
        import uuid

        echo = str(uuid.uuid4())
        payload = {
            "action": action,
            "params": params or {},
            "echo": echo,
        }

        try:
            await self._ws.send_json(payload)
            # 等待响应（简单实现，后续可优化为异步匹配）
            msg = await asyncio.wait_for(self._ws.receive(), timeout=10)
            data = json.loads(msg.data)
            if data.get("retcode") == 0:
                return data.get("data") if raw else True
            return None if raw else False
        except Exception as e:
            logger.error(f"WS API {action} error: {e}")
            return None if raw else False
