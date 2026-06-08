"""Cyber Girlfriend - 赛博女友主入口"""

import asyncio
import os
import sys
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

# 修复 Windows 终端中文编码
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from loguru import logger

# 加载环境变量
load_dotenv()

# 配置日志
logger.remove()
logger.add(sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{level:8}</level> | {message}")
logger.add("logs/app.log", rotation="10 MB", retention="7 days", level="DEBUG")

# 项目根目录
ROOT = Path(__file__).parent
CONFIG_DIR = ROOT / "config"

# ========== 全局组件 ==========
from core.llm import init_registry
from core.memory import MemoryManager, MemorySummarizer
from core.persona import PersonaLoader, PromptBuilder
from core.emotion import EmotionAnalyzer, EmotionEnhancer, MessageSegmenter

registry = init_registry(CONFIG_DIR / "settings.json")
memory_mgr = MemoryManager(str(ROOT / "data"))
persona_loader = PersonaLoader(CONFIG_DIR / "personas.json")
emotion_analyzer = EmotionAnalyzer()

# 每个用户的消息历史和短期记忆
_user_histories: dict[str, list[dict[str, str]]] = {}
_short_memories: dict[str, list[dict[str, str]]] = {}  # 短期记忆（原始对话）


def _get_time_context() -> str:
    """获取当前时间上下文"""
    now = datetime.now()
    hour = now.hour
    if 0 <= hour < 6:
        period = "深夜"
    elif 6 <= hour < 9:
        period = "早上"
    elif 9 <= hour < 12:
        period = "上午"
    elif 12 <= hour < 14:
        period = "中午"
    elif 14 <= hour < 18:
        period = "下午"
    elif 18 <= hour < 22:
        period = "晚上"
    else:
        period = "深夜"
    return f"现在是{period} {now.strftime('%Y-%m-%d %H:%M')}"


async def handle_message(user_id: str, content: str, persona_id: str = "girlfriend_001") -> str:
    """统一消息处理逻辑

    改进点（参考 My-Dream-Moments）：
    1. 注入时间上下文
    2. 情感分析 → 注入 prompt
    3. LLM 辅助记忆检索
    4. 回复分段发送
    5. 情感 emoji 增强
    6. 短期记忆 → 长期记忆总结
    """
    if not registry.available_models:
        return "我还没配置好模型呢，等等哦~"

    llm = registry.get()
    persona = persona_loader.get(persona_id)
    if not persona:
        return "我找不到我的人设了 (´;ω;`)"

    # 获取或创建消息历史
    if user_id not in _user_histories:
        _user_histories[user_id] = []
    if user_id not in _short_memories:
        _short_memories[user_id] = []
    messages = _user_histories[user_id]

    # 添加用户消息
    messages.append({"role": "user", "content": content})

    # 情感分析
    emotion = emotion_analyzer.analyze(content)

    # 时间上下文
    time_context = _get_time_context()

    # 记忆上下文（直接检索 + LLM 辅助）
    memory_context = memory_mgr.get_context_prompt(user_id, limit=8)

    # 构建 system prompt（增强版）
    system_prompt = PromptBuilder.build(
        persona,
        memory_context=memory_context,
        extra_instructions=f"时间：{time_context}\n用户当前情绪：{emotion.emotion.value}（强度 {emotion.intensity}）",
    )

    # 调用 LLM
    response = await llm.chat(messages=messages, system_prompt=system_prompt)
    reply = response.content

    # 情感 emoji 增强
    reply = EmotionEnhancer.enhance_reply(reply, emotion)

    # 添加助手回复
    messages.append({"role": "assistant", "content": reply})

    # 保存到短期记忆
    _short_memories[user_id].append({"user": content, "assistant": reply})

    # 自动提取记忆（关键词 + LLM 辅助）
    memory_mgr.add_memory(user_id, content)

    # 检查是否需要总结短期记忆（每 15 组对话总结一次）
    if len(_short_memories[user_id]) >= 15:
        summarizer = MemorySummarizer(llm)
        summary = await summarizer.summarize(_short_memories[user_id])
        if summary:
            memory_mgr.add_memory(user_id, summary, level=4, tags=["总结"])
            _short_memories[user_id] = []
            logger.info(f"Short memory summarized for {user_id}")

    # 保持消息历史不要太长
    if len(messages) > 20:
        _user_histories[user_id] = messages[-20:]

    logger.info(f"[{persona.name}] → {user_id}: {reply[:50]}...")
    return reply


# ========== 消息队列（借鉴 My-Dream-Moments 的 5 秒去抖） ==========
class MessageQueue:
    """消息队列 - 多条消息合并处理

    借鉴 My-Dream-Moments：用户可能连发多条消息，
    用 5 秒去抖定时器合并后再调用 LLM。
    """

    def __init__(self):
        self._queues: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def add(self, user_id: str, content: str, callback) -> None:
        """添加消息到队列"""
        with self._lock:
            if user_id not in self._queues:
                # 创建新队列，5 秒后处理
                timer = threading.Timer(5.0, self._process, args=[user_id, callback])
                self._queues[user_id] = {
                    "timer": timer,
                    "messages": [content],
                    "created_at": time.time(),
                }
                timer.start()
            else:
                # 取消旧定时器，重新计时
                self._queues[user_id]["timer"].cancel()
                self._queues[user_id]["messages"].append(content)
                timer = threading.Timer(5.0, self._process, args=[user_id, callback])
                self._queues[user_id]["timer"] = timer
                timer.start()

    def _process(self, user_id: str, callback) -> None:
        """处理队列中的消息"""
        with self._lock:
            if user_id not in self._queues:
                return
            queue_data = self._queues.pop(user_id)
            messages = queue_data["messages"]

        # 合并消息（用换行分隔）
        merged = "\n".join(messages)
        # 在主线程中异步执行回调
        asyncio.run(callback(user_id, merged))


msg_queue = MessageQueue()


# ========== FastAPI 应用 ==========
from webui.app import create_webui_app

app = create_webui_app(registry, memory_mgr, persona_loader)


@app.post("/api/wechat/webhook")
async def wechat_webhook(request: Request):
    """接收 ilink-wechat 的 webhook 回调"""
    try:
        data = await request.json()
        logger.info(f"[WeChat Webhook] {data}")

        user_id = data.get("from", "unknown")
        body = data.get("body", "")

        if not body:
            return {"text": ""}

        # 使用消息队列（5秒去抖）
        result = {"text": "", "done": False}

        async def process(uid, merged_msg):
            reply = await handle_message(uid, merged_msg)
            result["text"] = reply
            result["done"] = True

        msg_queue.add(user_id, body, lambda uid, msg: asyncio.run(process(uid, msg)))

        # 等待处理完成（最多 30 秒）
        for _ in range(300):
            if result["done"]:
                break
            await asyncio.sleep(0.1)

        return {"text": result["text"] or "思考中..."}
    except Exception as e:
        import traceback
        logger.error(f"WeChat webhook error: {e}\n{traceback.format_exc()}")
        return {"text": "抱歉，处理消息时出了点问题 (´;ω;`)"}


# 注：/api/chat 和 /api/health 由 webui.app 提供


# ========== 交互式聊天 ==========
async def chat_loop():
    """终端交互式聊天"""
    if not registry.available_models:
        logger.error("没有可用的模型！请检查 .env 文件中的 API Key 配置")
        return

    persona = persona_loader.get("girlfriend_001")
    if not persona:
        logger.error("默认人设 'girlfriend_001' 不存在")
        return

    logger.info(f"模型: {registry.get().model_name}")
    logger.info(f"人设: {persona.name} ({', '.join(persona.personality)})")
    logger.info("=" * 40)
    logger.info("开始聊天吧！输入 'quit' 退出")
    logger.info("=" * 40)

    while True:
        try:
            user_input = input("\n你: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input or user_input.lower() == "quit":
            break

        reply = await handle_message("local_user", user_input)

        # 分段显示
        segmented = MessageSegmenter.segment(reply)
        for i, seg in enumerate(segmented.segments):
            if i == 0:
                print(f"\n{persona.name}: {seg}")
            else:
                print(f"  {seg}")

    logger.info("聊天结束，拜拜~")


def main():
    """主入口"""
    import argparse

    parser = argparse.ArgumentParser(description="🎀 Cyber Girlfriend")
    parser.add_argument(
        "--mode",
        choices=["chat", "server"],
        default="chat",
        help="运行模式: chat=终端聊天, server=启动API服务",
    )
    parser.add_argument("--host", default="0.0.0.0", help="服务监听地址")
    parser.add_argument("--port", type=int, default=8080, help="服务监听端口")
    args = parser.parse_args()

    logger.info("🎀 Cyber Girlfriend 启动中...")
    logger.info(f"项目目录: {ROOT}")

    # 检查 .env
    if not (ROOT / ".env").exists():
        logger.warning(".env 文件不存在，请复制 .env.example 为 .env 并填写 API Key")

    if args.mode == "server":
        logger.info(f"启动 API 服务: http://{args.host}:{args.port}")
        logger.info(f"微信 Webhook: http://{args.host}:{args.port}/api/wechat/webhook")

        # 启动 QQ（如果配置了）
        napcat_ws = os.getenv("NAPCAT_WS_URL")
        napcat_http = os.getenv("NAPCAT_HTTP_URL")
        if napcat_ws or napcat_http:
            from transport.qq import QQTransport
            qq = QQTransport(
                ws_url=napcat_ws or "ws://127.0.0.1:3001",
                http_url=napcat_http or "",
                access_token=os.getenv("NAPCAT_ACCESS_TOKEN", ""),
            )
            qq.set_message_handler(lambda msg: handle_message(msg.user_id, msg.content))
            @app.on_event("startup")
            async def start_qq():
                async def _safe_start():
                    try:
                        await qq.start()
                    except Exception as e:
                        logger.warning(f"QQ transport failed: {e}")
                asyncio.create_task(_safe_start())
                logger.info("QQ transport started")

        # 启动 Telegram（如果配置了）
        tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
        if tg_token:
            from transport.telegram import TelegramTransport
            tg = TelegramTransport(bot_token=tg_token)
            tg.set_message_handler(lambda msg: handle_message(msg.user_id, msg.content))
            @app.on_event("startup")
            async def start_telegram():
                async def _safe_start():
                    try:
                        await tg.start()
                    except Exception as e:
                        logger.warning(f"Telegram transport failed: {e}")
                asyncio.create_task(_safe_start())
                logger.info("Telegram transport started")

        uvicorn.run(app, host=args.host, port=args.port)
    else:
        asyncio.run(chat_loop())


if __name__ == "__main__":
    main()
