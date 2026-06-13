"""WeChat Adapter — 微信适配器

基于 weixin-ilink 官方 SDK 实现微信 Bot 接入。

流程:
  1. 启动时显示二维码
  2. 用户扫码确认
  3. 保存凭证并启动长轮询
  4. 收到消息 → 通过 handler 回调处理
  5. 发送回复时自动回传 context_token

凭证存储:
  data/credentials/wechat.json — 扫码后自动保存
  data/credentials/wechat.json.sync — 长轮询游标（重启续传）
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from loguru import logger

from .base import BaseAdapter, AdapterMessage, AdapterConfig


# 凭证存储路径
_CREDENTIALS_DIR = Path(__file__).resolve().parent.parent / "data" / "credentials"
_CREDENTIALS_FILE = _CREDENTIALS_DIR / "wechat.json"
_SYNC_FILE = _CREDENTIALS_DIR / "wechat.json.sync"


def _qrcode_to_terminal(qr_url: str) -> None:
    """在终端打印 ASCII 二维码

    尝试用 qrcode 库生成，否则直接打印 URL。
    """
    try:
        import qrcode  # type: ignore[import]
        qr = qrcode.QRCode(border=1)
        qr.add_data(qr_url)
        qr.make()
        qr.print_ascii(invert=True)
    except Exception:
        print(f"\n[微信二维码] {qr_url}\n")


def _ensure_credentials_dir() -> None:
    _CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)


def _load_credentials() -> dict[str, Any] | None:
    if _CREDENTIALS_FILE.exists():
        try:
            return json.loads(_CREDENTIALS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


class WeChatAdapter(BaseAdapter):
    """微信适配器

    使用 weixin-ilink SDK 实现:
    - 二维码登录 / 自动保存凭证
    - 长轮询收消息
    - 发送文本 / 打字状态
    - context_token 自动管理
    """

    def __init__(self, config: AdapterConfig | None = None):
        if config is None:
            config = AdapterConfig(platform="wechat", enabled=True)
        super().__init__(config)

        self._bot = None
        self._credentials: dict[str, Any] | None = None
        self._running = False
        self._task: asyncio.Task | None = None

    # ---- 生命周期 ----

    async def start(self) -> None:
        """启动微信适配器

        1. 尝试复用已有凭证
        2. 否则启动二维码登录
        3. 启动长轮询消息接收
        """
        try:
            from weixin_ilink import WeixinBot, login
        except ImportError as e:
            logger.error(f"weixin-ilink not installed: {e}")
            print("\n  [错误] 微信 SDK 未安装")
            print("  请先运行: python install.py")
            return

        _ensure_credentials_dir()

        # 尝试复用已有凭证
        self._credentials = _load_credentials()

        if self._credentials:
            logger.info("WeChat: reusing existing credentials")
            try:
                self._bot = WeixinBot(
                    credentials=self._credentials,
                    cursor_file=str(_SYNC_FILE),
                    auto_save_cursor=True,
                )
            except Exception as e:
                logger.warning(f"WeChat credentials expired: {e}")
                self._credentials = None

        # 需要重新登录
        if not self._credentials:
            logger.info("WeChat: starting QR code login...")
            print("\n" + "=" * 50)
            print("  微信登录")
            print("=" * 50)
            print("\n  步骤：")
            print("  1. 确保手机上已安装微信 ClawBot 插件")
            print("  2. 打开微信，准备扫码")
            print("\n  正在获取二维码...")

            loop = asyncio.get_running_loop()

            def _on_qr(url: str) -> None:
                print("\n  请使用微信扫描下方二维码:\n")
                _qrcode_to_terminal(url)
                print("\n  等待扫码...")
                print("  （二维码 5 分钟后过期）")

            def _on_status(status: str) -> None:
                if status == "scaned":
                    print("\n  已扫码，请在手机上确认登录...")
                elif status == "confirmed":
                    print("\n  登录成功！")
                elif status == "expired":
                    print("\n  二维码已过期，正在重新获取...")

            try:
                creds = await loop.run_in_executor(
                    None,
                    lambda: login(
                        save_to=str(_CREDENTIALS_FILE),
                        on_qrcode=_on_qr,
                        on_status_change=_on_status,
                    ),
                )
                self._credentials = creds
                self._bot = WeixinBot(
                    credentials=creds,
                    cursor_file=str(_SYNC_FILE),
                    auto_save_cursor=True,
                )
            except Exception as e:
                logger.error(f"WeChat login failed: {e}")
                print(f"\n  [错误] 登录失败: {e}")
                print("  请检查：")
                print("  - 是否已安装微信 ClawBot 插件")
                print("  - 网络连接是否正常")
                raise

        # 启动消息轮询
        self._running = True
        self._task = asyncio.create_task(self._poll_messages())
        logger.info("WeChat adapter started")
        print("\n  微信 Bot 已启动")
        print("  现在可以通过微信发送消息给 AI 了")
        print("=" * 50 + "\n")

    async def stop(self) -> None:
        """停止微信适配器"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._bot:
            try:
                self._bot.stop()
            except Exception:
                pass
        logger.info("WeChat adapter stopped")

    # ---- 消息轮询 ----

    async def _poll_messages(self) -> None:
        """在后台线程中运行 weixin-ilink 的长轮询

        注意：bot.run() 内部使用 signal 模块，必须在主线程之外的
        独立线程中运行，不能用 run_in_executor（线程池线程）。
        """
        if not self._bot:
            return

        loop = asyncio.get_running_loop()

        # 注册消息处理回调
        def _handle_text(msg) -> None:
            """处理文本消息"""
            future = asyncio.run_coroutine_threadsafe(
                self._on_inbound_message(msg), loop
            )

            def _on_done(f):
                try:
                    f.result()
                except Exception as e:
                    logger.error(f"WeChat handler exception: {e}")

            future.add_done_callback(_on_done)

        self._bot.on_text(_handle_text)
        self._bot.on_image(lambda m: logger.debug(f"WeChat image from {m.from_user}"))

        # 在独立守护线程中运行 bot.run()（不能用 run_in_executor，
        # 因为 bot.run() 内部使用 signal 模块，只能在主线程中设置信号）
        import threading

        def _run_bot():
            import signal as _signal
            _original_signal = _signal.signal
            _signal.signal = lambda _signum, _handler: None
            try:
                self._bot.run()
            finally:
                _signal.signal = _original_signal

        bot_thread = threading.Thread(target=_run_bot, daemon=True)
        bot_thread.start()

        # 等待线程结束（或直到 self._running 变为 False）
        while self._running and bot_thread.is_alive():
            await asyncio.sleep(1)

        # 如果线程还在运行，说明需要停止
        if bot_thread.is_alive():
            try:
                self._bot.stop()
            except Exception:
                pass
            bot_thread.join(timeout=5)

    async def _on_inbound_message(self, msg) -> None:
        """将 weixin-ilink 消息转换为 AdapterMessage 并回调

        使用 msg.reply_text() 直接回复，SDK 自动处理 context_token。
        """
        if not self._handler:
            return

        loop = asyncio.get_running_loop()

        # 显示"正在输入"状态
        try:
            await loop.run_in_executor(None, lambda: msg.reply_typing())
        except Exception:
            pass

        # 构建统一消息格式
        user_id = f"wechat_{msg.from_user}"
        message = AdapterMessage(
            user_id=user_id,
            content=msg.text,
            message_id=str(msg.message_id),
            platform="wechat",
            timestamp="",
            metadata={
                "context_token": getattr(msg, "context_token", ""),
                "from_user": msg.from_user,
                "raw_message": msg,
            },
        )

        try:
            reply = await self._handler(message)
            if reply:
                # 使用 SDK 的 reply_text 方法，自动处理 context_token
                await loop.run_in_executor(None, lambda: msg.reply_text(reply))
                logger.info(f"WeChat reply to {msg.from_user}: {reply[:40]}...")
        except Exception as e:
            logger.error(f"WeChat handler error: {e}")
            # 发送错误提示
            try:
                await loop.run_in_executor(None, lambda: msg.reply_text("抱歉，处理消息时出错了，请稍后再试~"))
            except Exception:
                pass

    # ---- 发送 ----

    async def send(self, user_id: str, content: str, **kwargs) -> bool:
        """主动发送消息给微信用户"""
        if not self._bot:
            return False

        # 提取真实微信用户 ID
        raw_id = user_id.replace("wechat_", "")
        ctx_token = kwargs.get("context_token")

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: self._bot.send_text(
                    to=raw_id,
                    text=content,
                    context_token=ctx_token,
                ),
            )
            return True
        except Exception as e:
            logger.error(f"WeChat send error: {e}")
            return False

    async def reply(self, message: AdapterMessage, content: str, **kwargs) -> bool:
        """回复微信消息"""
        ctx_token = message.metadata.get("context_token")
        return await self.send(
            message.user_id,
            content,
            context_token=ctx_token,
            **kwargs,
        )

    async def send_typing(self, user_id: str) -> bool:
        """发送"正在输入"状态"""
        if not self._bot:
            return False

        raw_id = user_id.replace("wechat_", "")
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: self._bot.send_typing(to=raw_id),
            )
            return True
        except Exception as e:
            logger.error(f"WeChat typing error: {e}")
            return False

    def get_info(self) -> dict[str, Any]:
        """获取适配器信息"""
        info = super().get_info()
        info.update({
            "credentials_file": str(_CREDENTIALS_FILE),
            "has_credentials": _CREDENTIALS_FILE.exists(),
        })
        return info
