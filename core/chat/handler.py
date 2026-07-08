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

from loguru import logger

from core.chat.commands import Colors, CommandHandler
from core.config import DEFAULT_PERSONA_ID
from core.chat.pipeline import ChatPipeline
from core.dialogue import DialogueThinker
from core.dialogue.consistency import ConsistencyGuard
from core.dialogue.topic_tracker import TopicTracker
from core.multimodal import StickerReplier
from core.chat.display import (
    spinner_task, print_reply_token, print_reply_segmented,
    print_rel_change, get_welcome_message, SessionStats,
)


# ========== ChatHandler ==========

class ChatHandler:
    """聊天会话管理器：输入、输出、状态、生命周期"""

    def __init__(self, registry, memory_mgr, persona_loader, personality_engine,
                 chat_history, llm_emotion_analyzer,
                 proactive, mood_manager, config: dict,
                 tool_registry=None, open_loop=None, identity=None, life_summary=None,
                 relationship_tracker=None, affection_storage=None,
                 brain=None, mcp_manager=None, vision_manager=None):
        self._registry = registry
        self.memory_mgr = memory_mgr
        self.persona_loader = persona_loader
        self._personality_engine = personality_engine
        self.chat_history = chat_history
        self._llm_emotion_analyzer = llm_emotion_analyzer
        self.relationship_tracker = relationship_tracker
        self._proactive = proactive
        self._mood_manager = mood_manager
        self._personality_engine = personality_engine
        self._tool_registry = tool_registry
        self.config = config
        self._open_loop = open_loop
        self._identity = identity
        self._life_summary = life_summary
        self._affection_storage = affection_storage
        self._brain = brain
        self._mcp_manager = mcp_manager
        self._vision_manager = vision_manager

        # 当前人设 ID
        self.current_persona_id = DEFAULT_PERSONA_ID

        # 构建子组件
        llm = registry.get() if registry.available_models else None

        # v3.5 新组件
        dialogue_thinker = DialogueThinker(llm=llm) if llm else None
        sticker_replier = StickerReplier(use_ascii_art=False)
        consistency_guard = ConsistencyGuard(llm=llm) if llm else None
        topic_tracker = TopicTracker() if llm else None

        self.pipeline = ChatPipeline(
            llm, memory_mgr, persona_loader, personality_engine, chat_history,
            llm_emotion_analyzer, relationship_tracker, self._mood_manager, config,
            dialogue_thinker=dialogue_thinker,
            consistency_guard=consistency_guard,
            topic_tracker=topic_tracker,
            tool_registry=tool_registry,
            open_loop=open_loop,
            identity=identity,
            life_summary=life_summary,
            affection_storage=affection_storage,
            brain=brain,
        )
        # 挂载 MCP Manager 到 pipeline（用于工具调用）
        self.pipeline._mcp_manager = mcp_manager
        self.commands = CommandHandler(self)

    # ---- 内部 ----

    async def _process_and_respond(
        self,
        user_id: str,
        text: str,
        persona_name: str,
        stats: SessionStats,
        last_reply: list[str],
        *,
        clear_spinner: bool = False,
    ) -> None:
        """处理用户输入并流式输出 AI 回复

        Args:
            user_id: 用户 ID
            text: 用户输入文本
            persona_name: 当前人设名称
            stats: 会话统计对象
            last_reply: 用于累积回复 token 的列表（单元素）
            clear_spinner: 是否先清除 spinner 行（去抖模式用）
        """
        first_token = [True]
        spinner_stop = asyncio.Event()

        def _on_token(token: str):
            nonlocal first_token
            last_reply[0] += token
            if first_token[0]:
                spinner_stop.set()
                if clear_spinner:
                    print(f"\r{' ' * 50}\r", end="", flush=True)
                print_reply_token(persona_name, token, True)
                first_token[0] = False
            else:
                print_reply_token(persona_name, token, False)

        spinner = asyncio.create_task(
            spinner_task(spinner_stop, persona_name)
        )

        reply, rel_level = await self.pipeline.process(
            user_id, text, self.current_persona_id,
            on_token=_on_token,
        )

        if not spinner_stop.is_set():
            spinner_stop.set()
        spinner.cancel()
        stats.end_level = rel_level

        if first_token[0]:
            await print_reply_segmented(persona_name, reply, self.config)
        else:
            print()

        print_rel_change(rel_level)
        last_reply[0] = ""

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
        stats.start_level = int(self._affection_storage.get_level(
            user_id, persona_id=self.current_persona_id,
        )) if self._affection_storage else 50
        last_reply = [""]

        logger.info(f"模型: {self._registry.get().model_name}")
        logger.info(f"人设: {persona_name}")

        # 欢迎语
        welcome = get_welcome_message(persona, stats.start_level)
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
                    stats.message_count += count

                    await self._process_and_respond(
                        user_id, combined, persona_name, stats, last_reply,
                        clear_spinner=True,
                    )
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
                    await self._process_and_respond(
                        user_id, user_input, persona_name, stats, last_reply,
                    )
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
        stats.end_level = int(self._affection_storage.get_level(
            user_id, persona_id=self.current_persona_id,
        )) if self._affection_storage else 50
        print(stats.summary(persona_name))
