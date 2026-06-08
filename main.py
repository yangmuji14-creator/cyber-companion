"""Cyber Girlfriend - 赛博女友（纯 CMD 聊天）

运行方式：
    python main.py setup   — 首次运行设置向导
    python main.py         — 直接进聊天
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
from loguru import logger

load_dotenv()

ROOT = Path(__file__).parent
CONFIG_DIR = ROOT / "config"

# 日志
logger.remove()
logger.add(sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{level:8}</level> | {message}")
logger.add("logs/app.log", rotation="10 MB", retention="7 days", level="DEBUG")


# ========== 加载配置 ==========
def _load_advanced() -> dict:
    """从 settings.json 读取高级参数"""
    path = CONFIG_DIR / "settings.json"
    defaults = {
        "segment_max_length": 50,
        "debounce_seconds": 3,
        "summarize_threshold": 15,
    }
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            advanced = data.get("advanced", {})
            defaults.update({k: v for k, v in advanced.items() if k in defaults})
        except Exception:
            pass
    return defaults


ADVANCED = _load_advanced()


# ========== 核心组件 ==========
from core.llm import init_registry
from core.memory import MemoryManager, MemorySummarizer, ChatHistoryStorage
from core.persona import PersonaLoader, PromptBuilder
from core.emotion import EmotionAnalyzer, EmotionEnhancer, MessageSegmenter
from core.relationship import RelationshipTracker

registry = init_registry(CONFIG_DIR / "settings.json")
memory_mgr = MemoryManager(str(ROOT / "data"))
persona_loader = PersonaLoader(CONFIG_DIR / "personas.json")
emotion_analyzer = EmotionAnalyzer()
relationship_tracker = RelationshipTracker(str(ROOT / "data"))
chat_history = ChatHistoryStorage(str(ROOT / "data"), max_messages=20)


def _get_time_context() -> str:
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
    """统一消息处理逻辑"""
    if not registry.available_models:
        return "我还没配置好模型呢，等等哦~"

    llm = registry.get()
    persona = persona_loader.get(persona_id)
    if not persona:
        return "我找不到我的人设了 (´;ω;`)"

    messages = chat_history.get_messages(user_id)
    chat_history.add_message(user_id, "user", content)
    messages = chat_history.get_messages(user_id)

    emotion = emotion_analyzer.analyze(content)

    rel_level = relationship_tracker.update(
        user_id, emotion=emotion.emotion.value, base_level=persona.relationship_level
    )

    time_context = _get_time_context()
    memory_context = memory_mgr.get_context_prompt(user_id, limit=8)

    system_prompt = PromptBuilder.build(
        persona,
        memory_context=memory_context,
        extra_instructions=f"时间：{time_context}\n用户当前情绪：{emotion.emotion.value}（强度 {emotion.intensity}）",
        relationship_level=rel_level,
    )

    response = await llm.chat(messages=messages, system_prompt=system_prompt)
    reply = response.content

    reply = EmotionEnhancer.enhance_reply(reply, emotion)

    chat_history.add_message(user_id, "assistant", reply)
    chat_history.add_short_memory(user_id, content, reply)
    memory_mgr.add_memory(user_id, content)

    short_memories = chat_history.get_short_memories(user_id)
    if len(short_memories) >= ADVANCED["summarize_threshold"]:
        summarizer = MemorySummarizer(llm)
        summary = await summarizer.summarize(short_memories)
        if summary:
            memory_mgr.add_memory(user_id, summary, level=4, tags=["总结"])
            chat_history.clear_short_memories(user_id)
            logger.info(f"Short memory summarized for {user_id}")

    logger.info(f"[{persona.name}] → {user_id}: {reply[:80]}...")
    return reply


# ========== 聊天循环 ==========
async def chat_loop():
    """终端聊天"""
    persona = persona_loader.get("girlfriend_001")
    persona_name = persona.name if persona else "小雨"

    if not registry.available_models:
        logger.error("没有可用的模型！请先运行: python main.py setup")
        return

    logger.info(f"模型: {registry.get().model_name}")
    logger.info(f"人设: {persona_name}")
    logger.info("=" * 40)
    logger.info("开始聊天吧！输入 quit 退出")
    logger.info("=" * 40)

    loop = asyncio.get_event_loop()
    while True:
        try:
            user_input = await loop.run_in_executor(None, lambda: input("\n你: ").strip())
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input or user_input.lower() == "quit":
            break

        reply = await handle_message("local_user", user_input)

        segmented = MessageSegmenter.segment(reply, max_segment_length=ADVANCED["segment_max_length"])
        for i, seg in enumerate(segmented.segments):
            if i == 0:
                print(f"\n{persona_name}: {seg}")
            else:
                print(f"  {seg}")

    logger.info("拜拜~")


# ========== 主入口 ==========
def main():
    import argparse

    parser = argparse.ArgumentParser(description="🎀 Cyber Girlfriend")
    parser.add_argument(
        "command",
        nargs="?",
        default="run",
        choices=["setup", "run"],
        help="setup=设置向导, run=开始聊天（默认）",
    )
    args = parser.parse_args()

    if args.command == "setup":
        from setup import run_setup
        run_setup()
        return

    if not (ROOT / ".env").exists():
        logger.warning("未检测到 .env 文件，请先运行: python main.py setup")
        return

    logger.info("🎀 Cyber Girlfriend 启动中...")
    asyncio.run(chat_loop())


if __name__ == "__main__":
    main()
