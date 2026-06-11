"""ChatHandler — 聊天主循环

管理终端聊天会话：输入线程、消息去抖、流式输出、spinner动画、退出总结。

用法:
    handler = ChatHandler(registry, memory_mgr, persona_loader, chat_history,
                          llm_emotion_analyzer, relationship_tracker, proactive, config)
    asyncio.run(handler.run())
"""

import asyncio
import queue
import threading
from datetime import datetime

from loguru import logger

from core.chat.commands import Colors, CommandHandler
from core.chat.pipeline import ChatPipeline
from core.emotion import MessageSegmenter


# ========== Spinner 动画 ==========

_SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
_SPINNER_TEXT = " 正在思考..."


async def _spinner_task(stop_event: asyncio.Event, _persona_name: str):
    """后台 spinner 协程，每 0.12s 刷新一帧"""
    frame = 0
    while not stop_event.is_set():
        icon = _SPINNER_FRAMES[frame % len(_SPINNER_FRAMES)]
        print(f"\r  {Colors.DIM}{icon}{_SPINNER_TEXT}{Colors.RESET}", end="", flush=True)
        frame += 1
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=0.12)
            break
        except asyncio.TimeoutError:
            pass


# ========== 显示工具 ==========

def _print_reply_token(persona_name: str, token: str, is_first: bool):
    """流式打印一个 token"""
    if is_first:
        print(f"\n{Colors.MAGENTA}{persona_name}:{Colors.RESET} ", end="", flush=True)
    print(token, end="", flush=True)


async def _print_reply(persona_name: str, reply: str, advanced: dict):
    """分段打印 AI 回复（非流式回退用）"""
    segmented = MessageSegmenter.segment(
        reply, max_segment_length=advanced.get("segment_max_length", 50)
    )
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


# ========== 欢迎语 ==========

def _get_welcome_message(persona, rel_level: int) -> str:
    """根据时间和亲密度生成欢迎语（12 种变体）"""
    hour = datetime.now().hour

    if rel_level >= 80:
        if 0 <= hour < 6:
            return "你怎么这么晚还不睡呀？是不是在想我？哼哼~"
        elif 6 <= hour < 9:
            return "早安早安~ 今天也要元气满满哦！"
        elif 18 <= hour < 22:
            return "你回来啦~ 今天过得怎么样？我好想你！"
        else:
            return "嘿嘿，你来了~ 我一直在等你呢！"
    elif rel_level >= 40:
        if 0 <= hour < 6:
            return "这么晚还没睡呀？注意身体哦~"
        elif 6 <= hour < 9:
            return "早安~ 今天有什么安排吗？"
        elif 18 <= hour < 22:
            return "嗨~ 今天过得怎么样？"
        else:
            return "来啦~ 最近忙吗？"
    else:
        if 6 <= hour < 12:
            return "你好呀~ 今天天气不错呢！"
        elif 18 <= hour < 22:
            return "嗨，又见面了~"
        else:
            return "你好呀~"


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


# ========== ChatHandler ==========

class ChatHandler:
    """聊天会话管理器：输入、输出、状态、生命周期"""

    def __init__(self, registry, memory_mgr, persona_loader, chat_history,
                 llm_emotion_analyzer, relationship_tracker, proactive, config: dict):
        self._registry = registry
        self.memory_mgr = memory_mgr
        self.persona_loader = persona_loader
        self.chat_history = chat_history
        self._llm_emotion_analyzer = llm_emotion_analyzer
        self.relationship_tracker = relationship_tracker
        self._proactive = proactive
        self.config = config

        # 当前人设 ID
        self.current_persona_id = "girlfriend_001"

        # 构建子组件
        llm = registry.get() if registry.available_models else None
        self.pipeline = ChatPipeline(
            llm, memory_mgr, persona_loader, chat_history,
            llm_emotion_analyzer, relationship_tracker, config,
        )
        self.commands = CommandHandler(self)

    # ---- 主入口 ----

    async def run(self):
        """启动聊天循环"""
        persona = self.persona_loader.get(self.current_persona_id)
        persona_name = persona.name if persona else "小雨"
        debounce_seconds = self.config.get("debounce_seconds", 3)
        user_id = "local_user"

        if not self._registry.available_models:
            logger.error("没有可用的模型！请先运行: python main.py setup")
            return

        # 会话统计
        stats = SessionStats()
        stats.start_level = self.relationship_tracker.get_level(
            user_id, base_level=persona.relationship_level,
            persona_id=self.current_persona_id,
        )
        last_reply = [""]

        logger.info(f"模型: {self._registry.get().model_name}")
        logger.info(f"人设: {persona_name}")

        # 欢迎语
        welcome = _get_welcome_message(persona, stats.start_level)
        print(f"\n{Colors.MAGENTA}{persona_name}:{Colors.RESET} {welcome}")
        print(f"{Colors.DIM}输入 /help 查看可用命令{Colors.RESET}")
        if debounce_seconds > 0:
            print(f"{Colors.DIM}消息累积: 输入后 {debounce_seconds} 秒内可继续输入，合并后一起发送{Colors.RESET}")
        print()

        # 输入队列
        message_queue: list[str] = []
        input_q: queue.Queue[str | None] = queue.Queue()

        def _input_reader():
            """独立线程：持续读取用户输入"""
            while True:
                try:
                    line = input(f"{Colors.CYAN}你:{Colors.RESET} ").strip()
                    if not line:
                        continue
                    input_q.put(line)
                except (EOFError, KeyboardInterrupt):
                    input_q.put(None)
                    break

        input_thread = threading.Thread(target=_input_reader, daemon=True)
        input_thread.start()

        try:
            while True:
                try:
                    user_input = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: input_q.get(timeout=debounce_seconds)
                    )
                except (queue.Empty, Exception) as e:
                    if not isinstance(e, queue.Empty):
                        raise

                    # 超时 — 检查主动消息或发送累积消息
                    if not message_queue:
                        proactive_msg = self._proactive.check_proactive_messages(
                            user_id, self.current_persona_id
                        )
                        if proactive_msg:
                            persona_obj = self.persona_loader.get(self.current_persona_id)
                            p_name = persona_obj.name if persona_obj else "AI"
                            print(f"\n{Colors.YELLOW}💌 {p_name} 主动找你：{Colors.RESET}")
                            print(f"{Colors.MAGENTA}{p_name}:{Colors.RESET} {proactive_msg}")
                            print(f"{Colors.DIM}（AI 主动消息，无需回复~）{Colors.RESET}\n")
                        continue

                    # 发送累积消息
                    count = len(message_queue)
                    combined = "\n".join(message_queue)
                    message_queue = []

                    first_token = [True]
                    spinner_stop = asyncio.Event()

                    def _on_token(token: str):
                        nonlocal first_token
                        last_reply[0] += token
                        if first_token[0]:
                            spinner_stop.set()
                            print(f"\r{' ' * 50}\r", end="", flush=True)
                            _print_reply_token(persona_name, token, True)
                            first_token[0] = False
                        else:
                            _print_reply_token(persona_name, token, False)

                    spinner = asyncio.create_task(
                        _spinner_task(spinner_stop, persona_name)
                    )

                    reply, rel_level = await self.pipeline.process(
                        user_id, combined, self.current_persona_id,
                        on_token=_on_token,
                    )

                    if not spinner_stop.is_set():
                        spinner_stop.set()
                    spinner.cancel()
                    stats.message_count += count
                    stats.end_level = rel_level

                    if first_token[0]:
                        await _print_reply(persona_name, reply, self.config)
                    else:
                        print()

                    _print_rel_change(rel_level)
                    last_reply[0] = ""
                    continue

                # 收到输入
                if user_input is None or user_input.lower() in ("quit", "/quit"):
                    break

                # 斜杠命令
                if user_input.startswith("/"):
                    result = await self.commands.handle(
                        user_input, user_id, persona_name
                    )
                    if result == "quit":
                        break
                    if result is True:
                        continue

                # 不用去抖
                if debounce_seconds <= 0:
                    stats.message_count += 1

                    first_token = [True]
                    spinner_stop = asyncio.Event()

                    def _on_token_direct(token: str):
                        nonlocal first_token
                        last_reply[0] += token
                        if first_token[0]:
                            spinner_stop.set()
                            _print_reply_token(persona_name, token, True)
                            first_token[0] = False
                        else:
                            _print_reply_token(persona_name, token, False)

                    spinner = asyncio.create_task(
                        _spinner_task(spinner_stop, persona_name)
                    )

                    reply, rel_level = await self.pipeline.process(
                        user_id, user_input, self.current_persona_id,
                        on_token=_on_token_direct,
                    )

                    if not spinner_stop.is_set():
                        spinner_stop.set()
                    spinner.cancel()
                    stats.end_level = rel_level

                    if first_token[0]:
                        await _print_reply(persona_name, reply, self.config)
                    else:
                        print()

                    _print_rel_change(rel_level)
                    last_reply[0] = ""
                    continue

                # 加入消息队列（去抖模式）
                message_queue.append(user_input)
                count = len(message_queue)
                if count == 1:
                    print(f"  {Colors.DIM}⏳ 等待更多消息...（{debounce_seconds} 秒后发送）{Colors.RESET}", flush=True)
                else:
                    print(f"  {Colors.DIM}✓ 已收集 {count} 条消息，继续输入或等待发送{Colors.RESET}", flush=True)

        except asyncio.CancelledError:
            if last_reply[0]:
                self.chat_history.add_message(user_id, "assistant", last_reply[0])
                print(f"\n{Colors.DIM}（已保存部分回复）{Colors.RESET}")
        finally:
            input_q.put(None)

        # 退出总结
        stats.end_level = self.relationship_tracker.get_level(
            user_id, base_level=persona.relationship_level,
            persona_id=self.current_persona_id,
        )
        print(stats.summary(persona_name))
