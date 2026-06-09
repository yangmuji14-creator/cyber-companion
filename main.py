"""Cyber Girlfriend - 赛博女友（纯 CMD 聊天）

运行方式：
    python main.py setup   — 首次运行设置向导
    python main.py         — 直接进聊天
"""

import asyncio
import json
import os
import sys
import threading
import queue
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


# ========== ANSI 颜色 ==========
class Colors:
    """ANSI 颜色码（Windows 10+ 原生支持）"""
    CYAN = "\033[36m"      # 用户消息
    MAGENTA = "\033[35m"   # AI 回复
    YELLOW = "\033[33m"    # 系统消息
    GREEN = "\033[32m"     # 成功
    RED = "\033[31m"       # 错误
    DIM = "\033[2m"        # 暗淡（时间戳）
    BOLD = "\033[1m"       # 加粗
    RESET = "\033[0m"      # 重置


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
from core.emotion import EmotionAnalyzer, EmotionEnhancer, MessageSegmenter, LLMEmotionAnalyzer
from core.relationship import RelationshipTracker

registry = init_registry(CONFIG_DIR / "settings.json")
memory_mgr = MemoryManager(str(ROOT / "data"))
persona_loader = PersonaLoader(CONFIG_DIR / "personas.json")
emotion_analyzer = EmotionAnalyzer()  # 关键词分析（快速）
llm_emotion_analyzer = LLMEmotionAnalyzer()  # LLM 辅助（会在首次对话时初始化）
relationship_tracker = RelationshipTracker(str(ROOT / "data"))
chat_history = ChatHistoryStorage(str(ROOT / "data"), max_messages=20)


# ========== 会话统计 ==========
class SessionStats:
    """本次会话统计"""

    def __init__(self):
        self.message_count = 0
        self.memories_added = 0
        self.start_level = 0
        self.end_level = 0
        self.start_time = datetime.now()

    def summary(self, persona_name: str) -> str:
        """生成会话总结"""
        elapsed = (datetime.now() - self.start_time).total_seconds()
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)

        level_change = self.end_level - self.start_level
        if level_change > 0:
            level_str = f"{Colors.GREEN}+{level_change}{Colors.RESET}"
        elif level_change < 0:
            level_str = f"{Colors.RED}{level_change}{Colors.RESET}"
        else:
            level_str = "无变化"

        lines = [
            "",
            f"{Colors.YELLOW}{'=' * 40}{Colors.RESET}",
            f"{Colors.BOLD}📊 会话总结{Colors.RESET}",
            f"  ⏱  时长：{minutes}分{seconds}秒",
            f"  💬 消息：{self.message_count} 条",
            f"  🧠 新增记忆：{self.memories_added} 条",
            f"  💕 亲密度：{self.start_level} → {self.end_level}（{level_str}）",
            f"{Colors.YELLOW}{'=' * 40}{Colors.RESET}",
            f"{Colors.DIM}{persona_name}: 下次见啦~{Colors.RESET}",
        ]
        return "\n".join(lines)


# ========== 工具函数 ==========
def _format_multi_message(content: str) -> tuple[str, int]:
    """格式化多条合并消息

    Returns:
        (formatted_content, message_count) 元组
    """
    lines = [line.strip() for line in content.split("\n") if line.strip()]
    if len(lines) <= 1:
        return content, 1

    # 多条消息：格式化为清晰的列表
    formatted_parts = []
    for i, line in enumerate(lines, 1):
        formatted_parts.append(f"[消息{i}] {line}")

    return "\n".join(formatted_parts), len(lines)


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


def _timestamp() -> str:
    """当前时间 HH:MM"""
    return datetime.now().strftime("%H:%M")


def _get_welcome_message(persona, rel_level: int) -> str:
    """根据时间和亲密度生成欢迎语"""
    hour = datetime.now().hour

    if rel_level >= 80:
        # 恋人关系
        if 0 <= hour < 6:
            return "你怎么这么晚还不睡呀？是不是在想我？哼哼~"
        elif 6 <= hour < 9:
            return "早安早安~ 今天也要元气满满哦！"
        elif 18 <= hour < 22:
            return "你回来啦~ 今天过得怎么样？我好想你！"
        else:
            return "嘿嘿，你来了~ 我一直在等你呢！"
    elif rel_level >= 40:
        # 朋友以上
        if 0 <= hour < 6:
            return "这么晚还没睡呀？注意身体哦~"
        elif 6 <= hour < 9:
            return "早安~ 今天有什么安排吗？"
        elif 18 <= hour < 22:
            return "嗨~ 今天过得怎么样？"
        else:
            return "来啦~ 最近忙吗？"
    else:
        # 刚认识
        if 6 <= hour < 12:
            return "你好呀~ 今天天气不错呢！"
        elif 18 <= hour < 22:
            return "嗨，又见面了~"
        else:
            return "你好呀~"


# ========== 斜杠命令 ==========
COMMANDS = {
    "/help": "显示可用命令",
    "/stats": "查看亲密度统计",
    "/memories": "查看最近记忆",
    "/persona": "查看当前人设",
    "/clear": "清空聊天历史",
    "/export": "导出聊天记录",
    "/quit": "退出聊天",
}


async def handle_command(cmd: str, user_id: str, persona_name: str) -> bool:
    """处理斜杠命令

    Returns:
        True 如果命令已处理，False 如果不是命令
    """
    cmd = cmd.strip().lower()

    if cmd == "/help":
        print(f"\n{Colors.YELLOW}📖 可用命令：{Colors.RESET}")
        for name, desc in COMMANDS.items():
            print(f"  {Colors.CYAN}{name}{Colors.RESET} — {desc}")
        print()
        return True

    elif cmd == "/stats":
        stats = relationship_tracker.get_stats(user_id)
        days = stats.get("days_known", 0)
        level = stats.get("level", 50)
        msgs = stats.get("message_count", 0)
        pos = stats.get("positive_count", 0)
        neg = stats.get("negative_count", 0)

        # 亲密度等级描述
        if level >= 80:
            relation = "💕 恋人"
        elif level >= 60:
            relation = "💗 亲密"
        elif level >= 40:
            relation = "💛 朋友"
        elif level >= 20:
            relation = "🤍 熟悉"
        else:
            relation = "⬜ 陌生"

        print(f"\n{Colors.YELLOW}💕 亲密度统计{Colors.RESET}")
        print(f"  等级：{relation}（{level}/100）")
        print(f"  消息：{msgs} 条（👍 {pos} / 👎 {neg}）")
        print(f"  认识：{days:.0f} 天")
        print()
        return True

    elif cmd == "/memories":
        memories = memory_mgr.get_memories(user_id, limit=5)
        if not memories:
            print(f"\n{Colors.DIM}  还没有关于你的记忆~{Colors.RESET}\n")
        else:
            print(f"\n{Colors.YELLOW}🧠 最近记忆：{Colors.RESET}")
            for m in memories:
                stars = "⭐" * m.level
                print(f"  {stars} {m.content[:50]}")
            print()
        return True

    elif cmd == "/persona":
        persona = persona_loader.get("girlfriend_001")
        if persona:
            print(f"\n{Colors.YELLOW}🎀 人设信息{Colors.RESET}")
            print(f"  名字：{persona.name}")
            print(f"  年龄：{persona.age}岁")
            if persona.personality:
                print(f"  性格：{'、'.join(persona.personality)}")
            if persona.hobbies:
                hobbies = [h.get("name", "") for h in persona.hobbies[:3]]
                print(f"  爱好：{'、'.join(hobbies)}")
            if persona.catchphrases:
                print(f"  口头禅：{'、'.join(persona.catchphrases)}")
            print()
        return True

    elif cmd == "/clear":
        chat_history.delete_user(user_id)
        print(f"\n{Colors.GREEN}✅ 聊天历史已清空{Colors.RESET}\n")
        return True

    elif cmd == "/export":
        messages = chat_history.get_messages(user_id)
        if not messages:
            print(f"\n{Colors.DIM}  没有可导出的聊天记录{Colors.RESET}\n")
            return True

        export_dir = ROOT / "data" / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        filename = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = export_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)

        print(f"\n{Colors.GREEN}✅ 已导出到 {filepath}{Colors.RESET}\n")
        return True

    elif cmd == "/quit":
        return "quit"

    return False


# ========== 消息处理 ==========
async def handle_message(user_id: str, content: str, persona_id: str = "girlfriend_001") -> tuple[str, int]:
    """统一消息处理逻辑

    Returns:
        (reply_text, relationship_level) 元组
    """
    if not registry.available_models:
        return "我还没配置好模型呢，等等哦~", 50

    llm = registry.get()
    persona = persona_loader.get(persona_id)
    if not persona:
        return "我找不到我的人设了 (´;ω;`)", 50

    # 首次使用时初始化 LLM 情感分析器
    if llm_emotion_analyzer._llm is None:
        llm_emotion_analyzer._llm = llm

    # 格式化多消息：识别是否是多条合并的消息
    formatted_content, msg_count = _format_multi_message(content)

    # 存储格式化后的消息到聊天历史
    messages = chat_history.get_messages(user_id)
    chat_history.add_message(user_id, "user", formatted_content)
    messages = chat_history.get_messages(user_id)

    # 情感分析用原始内容（保留每条消息的情感）
    emotion = await llm_emotion_analyzer.analyze(content)

    rel_level = relationship_tracker.update(
        user_id, emotion=emotion.emotion.value, base_level=persona.relationship_level
    )

    time_context = _get_time_context()
    memory_context = memory_mgr.get_context_prompt(user_id, limit=8)

    # 记忆检索：找到与当前消息相关的记忆
    relevant_memories = await _retrieve_relevant_memories(user_id, content, llm)
    relevant_context = ""
    if relevant_memories:
        relevant_context = "\n【与当前话题相关的记忆】\n" + "\n".join(f"- {m}" for m in relevant_memories)

    # 构建 extra_instructions，多消息时增加上下文说明
    extra_instructions = f"时间：{time_context}\n用户当前情绪：{emotion.emotion.value}（强度 {emotion.intensity}）"
    if msg_count > 1:
        extra_instructions += (
            f"\n【重要】用户连续发了 {msg_count} 条消息，这是用户在短时间内快速输入的碎片化想法。"
            f"请把它们作为一个整体来理解用户的情绪和意图，"
            f"回复时自然地回应所有内容，不要逐条回复，也不要提到「你发了很多消息」之类的话。"
            f"像真人聊天一样，抓住重点，整体回应。"
        )

    system_prompt = PromptBuilder.build(
        persona,
        memory_context=memory_context + relevant_context,
        extra_instructions=extra_instructions,
        relationship_level=rel_level,
    )

    try:
        response = await llm.chat(messages=messages, system_prompt=system_prompt)
        reply = response.content
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        error_msg = _get_llm_error_message(e)
        return error_msg, rel_level

    reply = EmotionEnhancer.enhance_reply(reply, emotion)

    chat_history.add_message(user_id, "assistant", reply)
    chat_history.add_short_memory(user_id, content, reply)

    # 基础记忆存储（关键词评分）
    memory_mgr.add_memory(user_id, content)

    # LLM 辅助记忆提取（异步，不阻塞用户）
    asyncio.create_task(_background_extract_memory(user_id, content, reply, llm))

    # 异步总结（不阻塞用户）
    short_memories = chat_history.get_short_memories(user_id)
    if len(short_memories) >= ADVANCED["summarize_threshold"]:
        asyncio.create_task(_background_summarize(user_id, llm, short_memories))

    logger.debug(f"[{persona.name}] → {user_id}: {reply[:80]}...")
    return reply, rel_level


def _get_llm_error_message(error: Exception) -> str:
    """将 LLM 异常转为用户友好的中文消息"""
    error_str = str(error).lower()
    if "rate" in error_str or "429" in error_str:
        return "模型太忙了，稍等一下再试~ 🥺"
    elif "auth" in error_str or "401" in error_str or "api_key" in error_str:
        return "API key 好像有问题，检查一下配置哦~"
    elif "timeout" in error_str:
        return "网络有点慢，再试一次？"
    elif "connection" in error_str or "connect" in error_str:
        return "网络好像断了，检查一下网络连接~"
    else:
        return "哎呀，出了点小问题，再试一次？"


async def _background_summarize(user_id: str, llm, short_memories: list):
    """后台执行记忆总结"""
    try:
        summarizer = MemorySummarizer(llm)
        summary = await summarizer.summarize(short_memories)
        if summary:
            memory_mgr.add_memory(user_id, summary, level=4, tags=["总结"])
            chat_history.clear_short_memories(user_id)
            logger.info(f"Short memory summarized for {user_id}")
    except Exception as e:
        logger.warning(f"Background summarization failed: {e}")


async def _background_extract_memory(user_id: str, user_msg: str, assistant_reply: str, llm):
    """后台用 LLM 从对话中提取值得记住的信息"""
    try:
        summarizer = MemorySummarizer(llm)
        extracted = await summarizer.extract_memory(user_msg, assistant_reply)
        if extracted and extracted.get("content"):
            content = extracted["content"]
            importance = extracted.get("importance", 3)
            # 只有重要度 >= 2 才存储
            if importance >= 2:
                memory_mgr.add_memory(user_id, content, level=importance, tags=["自动提取"])
                logger.info(f"Auto-extracted memory [{importance}★]: {content[:30]}...")
    except Exception as e:
        logger.debug(f"Background memory extraction failed: {e}")


async def _retrieve_relevant_memories(user_id: str, query: str, llm) -> list[str]:
    """检索与当前消息相关的记忆"""
    try:
        # 获取所有记忆的内容
        all_memories = memory_mgr.get_memories(user_id, limit=30)
        if not all_memories:
            return []

        memory_texts = [m.content for m in all_memories]

        summarizer = MemorySummarizer(llm)
        relevant = await summarizer.retrieve_relevant(query, memory_texts, limit=3)
        return relevant
    except Exception as e:
        logger.debug(f"Memory retrieval failed: {e}")
        return []


# ========== 打印回复（统一逻辑） ==========
async def _print_reply(persona_name: str, reply: str):
    """分段打印 AI 回复，带打字延迟"""
    segmented = MessageSegmenter.segment(reply, max_segment_length=ADVANCED["segment_max_length"])
    for i, seg in enumerate(segmented.segments):
        if i == 0:
            print(f"\n{Colors.MAGENTA}{persona_name}:{Colors.RESET} {seg}", end="", flush=True)
        else:
            try:
                delay = MessageSegmenter.get_typing_delay(i, segmented.total_segments)
            except AttributeError:
                delay = 0
            if delay > 0:
                await asyncio.sleep(delay)
            print(f"\n  {seg}", end="", flush=True)
    print()


# ========== 聊天循环 ==========
async def chat_loop():
    """终端聊天（支持消息累积去抖 + 斜杠命令）"""
    persona = persona_loader.get("girlfriend_001")
    persona_name = persona.name if persona else "小雨"
    debounce_seconds = ADVANCED.get("debounce_seconds", 3)
    user_id = "local_user"

    if not registry.available_models:
        logger.error("没有可用的模型！请先运行: python main.py setup")
        return

    # 会话统计
    stats = SessionStats()
    stats.start_level = relationship_tracker.get_level(user_id, base_level=persona.relationship_level)

    logger.info(f"模型: {registry.get().model_name}")
    logger.info(f"人设: {persona_name}")

    # 欢迎语
    welcome = _get_welcome_message(persona, stats.start_level)
    print(f"\n{Colors.MAGENTA}{persona_name}:{Colors.RESET} {welcome}")
    print(f"{Colors.DIM}输入 /help 查看可用命令{Colors.RESET}")
    if debounce_seconds > 0:
        print(f"{Colors.DIM}消息累积: 输入后 {debounce_seconds} 秒内可继续输入，合并后一起发送{Colors.RESET}")
    print()

    message_queue: list[str] = []
    input_q: queue.Queue[str | None] = queue.Queue()

    def _input_reader():
        """独立线程：持续读取用户输入"""
        while True:
            try:
                line = input(f"{Colors.CYAN}你:{Colors.RESET} ").strip()
                if not line:
                    continue  # 空输入（直接回车）跳过
                input_q.put(line)
            except (EOFError, KeyboardInterrupt):
                input_q.put(None)
                break

    # 启动输入线程
    input_thread = threading.Thread(target=_input_reader, daemon=True)
    input_thread.start()

    try:
        while True:
            # 等待用户输入，超时时间 = debounce_seconds
            try:
                user_input = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: input_q.get(timeout=debounce_seconds)
                )
            except (queue.Empty, Exception) as e:
                if not isinstance(e, queue.Empty):
                    raise
                # 超时 → 倒计时结束，发送累积的消息
                if not message_queue:
                    continue

                count = len(message_queue)
                combined = "\n".join(message_queue)
                message_queue = []

                print(f"  {Colors.DIM}💭 发送 {count} 条消息，思考中...{Colors.RESET}", end="", flush=True)
                reply, rel_level = await handle_message(user_id, combined)
                stats.message_count += count
                stats.end_level = rel_level
                print(f"\r{' ' * 50}\r", end="", flush=True)

                await _print_reply(persona_name, reply)
                _print_rel_change(rel_level)
                continue

            # 收到输入
            if user_input is None or user_input.lower() in ("quit", "/quit"):
                break

            # 斜杠命令
            if user_input.startswith("/"):
                result = await handle_command(user_input, user_id, persona_name)
                if result == "quit":
                    break
                if result is True:
                    continue

            # 不用去抖模式
            if debounce_seconds <= 0:
                stats.message_count += 1
                reply, rel_level = await handle_message(user_id, user_input)
                stats.end_level = rel_level
                await _print_reply(persona_name, reply)
                _print_rel_change(rel_level)
                continue

            # 加入消息队列
            message_queue.append(user_input)
            count = len(message_queue)
            if count == 1:
                print(f"  {Colors.DIM}⏳ 等待更多消息...（{debounce_seconds} 秒后发送）{Colors.RESET}", flush=True)
            else:
                print(f"  {Colors.DIM}✓ 已收集 {count} 条消息，继续输入或等待发送{Colors.RESET}", flush=True)

    except asyncio.CancelledError:
        pass
    finally:
        # 清理输入线程
        input_q.put(None)

    # 退出总结
    stats.end_level = relationship_tracker.get_level(user_id, base_level=persona.relationship_level)
    print(stats.summary(persona_name))


def _print_rel_change(level: int):
    """显示亲密度变化提示"""
    if level >= 80:
        icon = "💕"
    elif level >= 60:
        icon = "💗"
    elif level >= 40:
        icon = "💛"
    else:
        icon = "🤍"
    print(f"  {Colors.DIM}{icon} 亲密度 {level}/100{Colors.RESET}")


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
    try:
        asyncio.run(chat_loop())
    except KeyboardInterrupt:
        print()
        logger.info("拜拜~")


if __name__ == "__main__":
    main()
