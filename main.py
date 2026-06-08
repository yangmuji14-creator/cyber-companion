"""Cyber Girlfriend - 赛博女友主入口"""

import asyncio
import os
import sys
from pathlib import Path

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
from core.memory import MemoryManager
from core.persona import PersonaLoader, PromptBuilder

registry = init_registry(CONFIG_DIR / "settings.json")
memory_mgr = MemoryManager(str(ROOT / "data"))
persona_loader = PersonaLoader(CONFIG_DIR / "personas.json")

# 每个用户的消息历史（内存中，重启清空）
_user_histories: dict[str, list[dict[str, str]]] = {}


async def handle_message(user_id: str, content: str, persona_id: str = "girlfriend_001") -> str:
    """统一消息处理逻辑

    Args:
        user_id: 用户 ID
        content: 消息内容
        persona_id: 人设 ID

    Returns:
        回复文本
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
    messages = _user_histories[user_id]

    # 添加用户消息
    messages.append({"role": "user", "content": content})

    # 构建 system prompt（人设 + 记忆上下文）
    memory_context = memory_mgr.get_context_prompt(user_id)
    system_prompt = PromptBuilder.build(persona, memory_context=memory_context)

    # 调用 LLM
    response = await llm.chat(messages=messages, system_prompt=system_prompt)

    # 添加助手回复
    messages.append({"role": "assistant", "content": response.content})

    # 自动提取记忆
    memory_mgr.add_memory(user_id, content)

    # 保持消息历史不要太长
    if len(messages) > 20:
        _user_histories[user_id] = messages[-20:]

    logger.info(f"[{persona.name}] → {user_id}: {response.content[:50]}...")
    return response.content


# ========== FastAPI 应用 ==========
app = FastAPI(title="Cyber Girlfriend", description="🎀 赛博女友 API")


@app.post("/api/wechat/webhook")
async def wechat_webhook(request: Request):
    """接收 ilink-wechat 的 webhook 回调"""
    data = await request.json()
    logger.info(f"[WeChat Webhook] {data}")

    user_id = data.get("from", "unknown")
    body = data.get("body", "")

    if not body:
        return {"text": ""}

    reply = await handle_message(user_id, body)
    return {"text": reply}


@app.post("/api/chat")
async def chat_api(request: Request):
    """通用聊天 API（给 WebUI 用）"""
    data = await request.json()
    user_id = data.get("user_id", "web_user")
    content = data.get("content", "")

    if not content:
        return {"error": "content is required"}

    reply = await handle_message(user_id, content)
    return {"reply": reply}


@app.get("/api/health")
async def health():
    """健康检查"""
    return {
        "status": "ok",
        "models": registry.available_models,
        "default_model": registry.default_model,
    }


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
        print(f"\n{persona.name}: {reply}")

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
        uvicorn.run(app, host=args.host, port=args.port)
    else:
        asyncio.run(chat_loop())


if __name__ == "__main__":
    main()
