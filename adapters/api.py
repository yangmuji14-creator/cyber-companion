"""API Adapter — REST API 适配器

提供 HTTP API 接口，允许外部系统与 AI 对话。
"""

import asyncio
import json
from datetime import datetime
from typing import Any

from loguru import logger

from .base import BaseAdapter, AdapterMessage, AdapterConfig


class APIAdapter(BaseAdapter):
    """REST API 适配器"""

    def __init__(self, config: AdapterConfig | None = None, host: str = "0.0.0.0", port: int = 8080):
        if config is None:
            config = AdapterConfig(platform="api")
        super().__init__(config)

        self._host = host
        self._port = port
        self._app = None
        self._runner = None

    async def start(self) -> None:
        """启动 API 服务器"""
        try:
            from aiohttp import web
        except ImportError:
            logger.error("aiohttp not installed. Run: pip install aiohttp")
            return

        self._app = web.Application()
        self._app.router.add_post("/chat", self._handle_chat)
        self._app.router.add_get("/health", self._handle_health)
        self._app.router.add_get("/info", self._handle_info)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self._host, self._port)
        await site.start()
        logger.info(f"API server started on {self._host}:{self._port}")

    async def stop(self) -> None:
        """停止 API 服务器"""
        if self._runner:
            await self._runner.cleanup()
        logger.info("API server stopped")

    async def _handle_chat(self, request):
        """处理 /chat 请求"""
        from aiohttp import web

        try:
            data = await request.json()
            user_id = data.get("user_id", "api_user")
            content = data.get("content", "")

            if not content:
                return web.json_response({"error": "content is required"}, status=400)

            # 创建消息
            message = AdapterMessage(
                user_id=user_id,
                content=content,
                platform="api",
                timestamp=datetime.now().isoformat(),
                metadata=data.get("metadata", {}),
            )

            # 调用处理回调
            if self._handler:
                reply = await self._handler(message)
            else:
                reply = "No handler configured"

            return web.json_response({
                "reply": reply,
                "user_id": user_id,
                "timestamp": datetime.now().isoformat(),
            })

        except Exception as e:
            logger.error(f"Chat handler error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def _handle_health(self, request):
        """处理 /health 请求"""
        from aiohttp import web
        return web.json_response({"status": "ok"})

    async def _handle_info(self, request):
        """处理 /info 请求"""
        from aiohttp import web
        return web.json_response(self.get_info())

    async def send(self, user_id: str, content: str, **kwargs) -> bool:
        """API 适配器不支持主动发送（被动响应）"""
        logger.warning("API adapter does not support主动发送")
        return False

    async def reply(self, message: AdapterMessage, content: str, **kwargs) -> bool:
        """回复消息（通过 HTTP 响应）"""
        # API 适配器的回复通过 HTTP 响应返回，不需要单独发送
        return True

    def get_info(self) -> dict[str, Any]:
        """获取适配器信息"""
        info = super().get_info()
        info.update({
            "host": self._host,
            "port": self._port,
            "endpoints": ["/chat", "/health", "/info"],
        })
        return info
