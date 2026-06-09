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

    logger.debug(f"[{persona.name}] → {user_id}: {reply[:80]}...")
    return reply


# ========== 聊天循环 ==========
async def chat_loop():
    """终端聊天（支持消息累积去抖）

    用户可以在倒计时期间继续输入，新消息加入队列并重置倒计时。
    倒计时结束后，所有累积的消息合并后一次性发给模型。
    """
    persona = persona_loader.get("girlfriend_001")
    persona_name = persona.name if persona else "小雨"
    debounce_seconds = ADVANCED.get("debounce_seconds", 3)

    if not registry.available_models:
        logger.error("没有可用的模型！请先运行: python main.py setup")
        return

    logger.info(f"模型: {registry.get().model_name}")
    logger.info(f"人设: {persona_name}")
    logger.info("=" * 40)
    logger.info("开始聊天吧！输入 quit 退出")
    if debounce_seconds > 0:
        logger.info(f"消息累积: 输入后 {debounce_seconds} 秒内可继续输入，合并后一起发送")
    logger.info("=" * 40)

    message_queue: list[str] = []  # 累积的消息队列
    input_event = asyncio.Event()  # 有新输入时触发
    countdown_active = asyncio.Event()  # 倒计时正在进行

    async def countdown_timer():
        """倒计时：每隔 1 秒更新显示，倒计时结束后触发处理"""
        nonlocal message_queue
        while True:
            await input_event.wait()
            input_event.clear()

            # 开始倒计时
            countdown_active.set()
            for remaining in range(debounce_seconds, 0, -1):
                count = len(message_queue)
                label = f"（{count} 条消息）" if count > 1 else ""
                print(f"\r  ⏳ {remaining} 秒后发送{label}  ", end="", flush=True)
                try:
                    await asyncio.wait_for(input_event.wait(), timeout=1.0)
                    # 有新输入，重置倒计时
                    input_event.clear()
                    remaining = debounce_seconds  # 重置
                    continue
                except asyncio.TimeoutError:
                    pass

            # 倒计时结束，合并发送
            count = len(message_queue)
            if count == 0:
                countdown_active.clear()
                continue

            # 合并所有消息
            combined = "\n".join(message_queue)
            message_queue = []
            countdown_active.clear()

            # 清除倒计时行
            print(f"\r{' ' * 50}\r", end="", flush=True)
            print(f"  💭 发送 {count} 条消息，思考中...", end="", flush=True)

            reply = await handle_message("local_user", combined)

            # 清除"思考中"提示
            print(f"\r{' ' * 50}\r", end="", flush=True)

            # 分段打印回复
            segmented = MessageSegmenter.segment(reply, max_segment_length=ADVANCED["segment_max_length"])
            for i, seg in enumerate(segmented.segments):
                if i == 0:
                    print(f"\n{persona_name}: {seg}", end="", flush=True)
                else:
                    delay = MessageSegmenter.get_typing_delay(i, segmented.total_segments)
                    if delay > 0:
                        await asyncio.sleep(delay)
                    print(f"\n  {seg}", end="", flush=True)
            print()

    # 启动倒计时任务
    timer_task = asyncio.create_task(countdown_timer())

    loop = asyncio.get_event_loop()
    try:
        while True:
            try:
                user_input = await loop.run_in_executor(None, lambda: input("\n你: ").strip())
            except (EOFError, KeyboardInterrupt):
                break

            if not user_input or user_input.lower() == "quit":
                break

            if debounce_seconds <= 0:
                # 不用去抖，直接发送
                reply = await handle_message("local_user", user_input)
                segmented = MessageSegmenter.segment(reply, max_segment_length=ADVANCED["segment_max_length"])
                for i, seg in enumerate(segmented.segments):
                    if i == 0:
                        print(f"\n{persona_name}: {seg}", end="", flush=True)
                    else:
                        delay = MessageSegmenter.get_typing_delay(i, segmented.total_segments)
                        if delay > 0:
                            await asyncio.sleep(delay)
                        print(f"\n  {seg}", end="", flush=True)
                print()
            else:
                # 加入消息队列，触发/重置倒计时
                message_queue.append(user_input)
                count = len(message_queue)
                if count > 1:
                    print(f"  ✓ 已收集 {count} 条消息，继续输入或等待发送")
                input_event.set()
    finally:
        timer_task.cancel()
        try:
            await timer_task
        except asyncio.CancelledError:
            pass

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
