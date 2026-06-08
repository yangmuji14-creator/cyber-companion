"""Telegram Bot 接入"""

from typing import Any

from loguru import logger
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from ..base import BaseTransport, IncomingMessage, OutgoingMessage


class TelegramTransport(BaseTransport):
    """Telegram 传输层

    使用 python-telegram-bot 库接入 Telegram Bot API。
    """

    def __init__(self, bot_token: str):
        self._token = bot_token
        self._app: Application | None = None
        self._handler = None

    @property
    def platform(self) -> str:
        return "telegram"

    def set_message_handler(self, handler) -> None:
        """设置消息处理回调"""
        self._handler = handler

    async def start(self) -> None:
        """启动 Telegram Bot"""
        self._app = (
            Application.builder()
            .token(self._token)
            .build()
        )

        # 注册命令处理器
        self._app.add_handler(CommandHandler("start", self._cmd_start))
        self._app.add_handler(CommandHandler("help", self._cmd_help))

        # 注册消息处理器
        self._app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_text)
        )

        logger.info("Telegram bot starting...")
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling()
        logger.info("Telegram bot started")

    async def stop(self) -> None:
        """停止 Telegram Bot"""
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
        logger.info("Telegram bot stopped")

    async def send_message(self, user_id: str, message: OutgoingMessage) -> bool:
        """主动发送消息"""
        if not self._app:
            return False
        try:
            await self._app.bot.send_message(chat_id=int(user_id), text=message.content)
            return True
        except Exception as e:
            logger.error(f"Telegram send error: {e}")
            return False

    # ========== 内部处理器 ==========

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """处理 /start 命令"""
        await update.message.reply_text(
            "你好呀~我是你的赛博女友！🎀\n发消息给我就可以聊天啦~"
        )

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """处理 /help 命令"""
        await update.message.reply_text(
            "💬 直接发消息就可以和我聊天\n"
            "🧠 我会记住你说过的重要事情\n"
            "🎀 我是小雨，请多关照~"
        )

    async def _handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """处理文本消息"""
        if not update.message or not update.message.text:
            return

        user_id = str(update.effective_user.id)
        content = update.message.text

        logger.info(f"[Telegram] 收到消息 from={user_id}: {content[:50]}...")

        if self._handler:
            msg = IncomingMessage(
                platform="telegram",
                user_id=user_id,
                content=content,
                raw_data={"update": update.to_dict()},
            )
            try:
                reply_text = await self._handler(msg)
                await update.message.reply_text(reply_text)
            except Exception as e:
                logger.error(f"Handler error: {e}")
                await update.message.reply_text("抱歉，处理消息时出了点问题 (´;ω;`)")
