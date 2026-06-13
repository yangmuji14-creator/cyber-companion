"""Application factory — 组件初始化与依赖注入

将 main.py 的组件创建逻辑提取到此模块，使 main.py 只负责 CLI 入口。
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from core.config import ROOT, CONFIG_DIR, load_advanced
from core.llm import init_registry, LLMRegistry
from core.memory import MemoryManager, ChatHistoryStorage, OpenLoopEngine, IdentityLayer, LifeSummaryEngine
from core.memory.embedder import SentenceTransformerEmbedder
from core.memory.vector_store import VectorStore
from core.persona import PersonaLoader
from core.personality import PersonalityEngine
from core.emotion import LLMEmotionAnalyzer
from core.relationship import RelationshipTracker
from core.proactive import ProactiveMessenger
from core.emotion.mood import MoodEngine
from core.chat import ChatHandler


@dataclass
class AppComponents:
    """持有所有初始化后的组件"""
    registry: LLMRegistry
    memory_mgr: MemoryManager
    persona_loader: PersonaLoader
    personality_engine: PersonalityEngine
    chat_history: ChatHistoryStorage
    llm_emotion_analyzer: LLMEmotionAnalyzer
    relationship_tracker: RelationshipTracker
    mood_manager: MoodEngine
    proactive: ProactiveMessenger
    open_loop: OpenLoopEngine
    identity: IdentityLayer
    life_summary: LifeSummaryEngine
    handler: ChatHandler
    advanced_config: dict


def create_components(data_dir: str | Path | None = None) -> AppComponents:
    """创建并组装所有核心组件

    Args:
        data_dir: 数据存储目录，默认 ROOT/data

    Returns:
        所有组件的容器
    """
    root = ROOT if data_dir is None else Path(data_dir)
    config = load_advanced()

    registry = init_registry(CONFIG_DIR / "settings.json")

    embedder = SentenceTransformerEmbedder()
    vector_store = VectorStore(str(root / "data" / "vectors.db"))

    memory_mgr = MemoryManager(
        str(root / "data"),
        embedder=embedder,
        vector_store=vector_store,
    )
    persona_loader = PersonaLoader(CONFIG_DIR / "personas.json")
    personality_engine = PersonalityEngine(str(root / "data"))
    llm_emotion_analyzer = LLMEmotionAnalyzer()
    relationship_tracker = RelationshipTracker(str(root / "data"))
    chat_history = ChatHistoryStorage(
        str(root / "data"), max_messages=config["max_messages"]
    )
    mood_manager = MoodEngine(str(root / "data"))

    # v1.2/v1.3 新增组件
    open_loop = OpenLoopEngine(str(root / "data"))
    identity = IdentityLayer(str(root / "data"))
    life_summary = LifeSummaryEngine(str(root / "data"))

    proactive = ProactiveMessenger(
        persona_loader, memory_mgr, relationship_tracker,
        mood_engine=mood_manager,
        config=config,
    )

    handler = ChatHandler(
        registry=registry,
        memory_mgr=memory_mgr,
        persona_loader=persona_loader,
        personality_engine=personality_engine,
        chat_history=chat_history,
        llm_emotion_analyzer=llm_emotion_analyzer,
        relationship_tracker=relationship_tracker,
        proactive=proactive,
        mood_manager=mood_manager,
        config=config,
        open_loop=open_loop,
        identity=identity,
        life_summary=life_summary,
    )

    return AppComponents(
        registry=registry,
        memory_mgr=memory_mgr,
        persona_loader=persona_loader,
        personality_engine=personality_engine,
        chat_history=chat_history,
        llm_emotion_analyzer=llm_emotion_analyzer,
        relationship_tracker=relationship_tracker,
        mood_manager=mood_manager,
        proactive=proactive,
        open_loop=open_loop,
        identity=identity,
        life_summary=life_summary,
        handler=handler,
        advanced_config=config,
    )


class DebounceState:
    """消息去抖状态（按平台 + 用户隔离）"""

    def __init__(self, platform: str, user_id: str, timeout: float,
                 pipeline, app: AppComponents, manager: "AdapterManager"):
        self.platform = platform
        self.user_id = user_id
        self.timeout = timeout
        self.pipeline = pipeline
        self.app = app
        self.manager = manager
        self.queue: list[str] = []
        self._timer_task: asyncio.Task | None = None

    async def add(self, text: str) -> None:
        """添加消息到去抖队列"""
        self.queue.append(text)
        await self._reset_timer()

    async def _reset_timer(self) -> None:
        if self._timer_task:
            self._timer_task.cancel()
        self._timer_task = asyncio.create_task(self._debounce_timer())

    async def _debounce_timer(self) -> None:
        try:
            await asyncio.sleep(self.timeout)
            await self.flush()
        except asyncio.CancelledError:
            pass

    async def flush(self) -> None:
        """立即处理队列中所有消息"""
        if not self.queue:
            return
        combined = "\n".join(self.queue)
        self.queue = []
        self._timer_task = None
        try:
            reply, _ = await self.pipeline.process(
                self.user_id, combined, "girlfriend_001"
            )
            # 通过适配器发送回复
            adapter = self.manager.get(self.platform)
            if adapter:
                await adapter.send(self.user_id, reply)
        except Exception as e:
            logger.error(f"Debounce flush error ({self.platform}/{self.user_id}): {e}")


class DebounceManager:
    """统一消息去抖管理器"""

    def __init__(self, timeout: float, pipeline, app: AppComponents, manager: "AdapterManager"):
        self.timeout = timeout
        self.pipeline = pipeline
        self.app = app
        self.manager = manager
        self._states: dict[str, DebounceState] = {}

    def _key(self, platform: str, user_id: str) -> str:
        return f"{platform}:{user_id}"

    async def add_message(self, platform: str, user_id: str, text: str) -> None:
        """添加消息到去抖队列"""
        key = self._key(platform, user_id)
        if key not in self._states:
            self._states[key] = DebounceState(
                platform, user_id, self.timeout,
                self.pipeline, self.app, self.manager,
            )
        await self._states[key].add(text)

    async def flush_all(self) -> None:
        """立即刷新所有队列"""
        for state in self._states.values():
            await state.flush()


async def run_with_adapters(app: AppComponents, platforms: list[str]) -> None:
    """启动多平台适配器模式

    所有平台共享同一个 ChatPipeline，支持消息去抖合并。
    CLI 保留流式输出、命令处理等完整体验。
    """
    from adapters import AdapterManager
    from adapters.cli import CLIAdapter
    from adapters.wechat import WeChatAdapter
    from adapters.api import APIAdapter
    from adapters.base import AdapterConfig
    from core.chat.commands import Colors, CommandHandler
    from core.chat.handler import SessionStats, _get_welcome_message, _print_reply_token, _print_rel_change, _spinner_task

    manager = AdapterManager()

    # 共享 pipeline（从 ChatHandler 复用）
    pipeline = app.handler.pipeline
    debounce_seconds = app.advanced_config.get("debounce_seconds", 3)

    # 统一去抖管理器
    debounce = DebounceManager(debounce_seconds, pipeline, app, manager)

    # 注册 CLI（始终启用）
    cli = CLIAdapter()
    manager.register(cli)

    # 注册指定平台
    for platform in platforms:
        if platform == "wechat":
            manager.register(WeChatAdapter())
        elif platform == "api":
            manager.register(APIAdapter())

    # 设置消息处理回调（给 WeChat 等外部平台使用）
    async def _handle_message(message):
        """外部平台消息处理：加入去抖队列"""
        if message.platform == "cli":
            # CLI 不走这里，走下面的主循环
            return ""
        # WeChat 等平台：加入去抖队列，不立即回复
        await debounce.add_message(message.platform, message.user_id, message.content)
        return ""  # 返回空，让适配器不立即回复

    manager.set_message_handler(_handle_message)

    # 启动所有适配器
    await manager.start_all()

    # ---- CLI 用户信息 ----
    user_id = "local_user"
    persona = app.persona_loader.get("girlfriend_001")
    persona_name = persona.name if persona else "小雨"

    # 会话统计
    stats = SessionStats()
    stats.start_level = app.relationship_tracker.get_level(
        user_id, base_level=getattr(persona, 'relationship_level', 50),
        persona_id="girlfriend_001",
    )
    last_reply = [""]

    # CLI 斜杠命令处理器（本地处理，不走 pipeline）
    cli_commands = CommandHandler(app.handler)

    logger.info(f"多平台模式已启动: {platforms}")
    logger.info(f"模型: {app.registry.get().model_name}")
    logger.info(f"人设: {persona_name}")

    # 欢迎语
    welcome = _get_welcome_message(persona, stats.start_level)
    print(f"\n{Colors.MAGENTA}{persona_name}:{Colors.RESET} {welcome}")
    print(f"{Colors.DIM}输入 /help 查看可用命令{Colors.RESET}")
    if debounce_seconds > 0:
        print(f"{Colors.DIM}消息累积: 输入后 {debounce_seconds} 秒内可继续输入，合并后一起发送{Colors.RESET}")
    print()

    # CLI 消息去抖队列
    cli_message_queue: list[str] = []
    cli_debounce_key = f"cli:{user_id}"

    # ========== 主循环 ==========
    try:
        while True:
            # 尝试读取 CLI 输入（非阻塞）
            user_input = await cli.get_input(timeout=0.5)

            if user_input is not None:
                if user_input.strip().lower() in ("/quit", "quit"):
                    logger.info("用户请求退出")
                    break

                # 斜杠命令
                if user_input.startswith("/"):
                    result = await cli_commands.handle(
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

                    def _on_token(token: str):
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

                    reply, rel_level = await pipeline.process(
                        user_id, user_input, "girlfriend_001",
                        on_token=_on_token,
                    )

                    if not spinner_stop.is_set():
                        spinner_stop.set()
                    spinner.cancel()
                    stats.end_level = rel_level

                    if first_token[0]:
                        print(f"\n{Colors.MAGENTA}{persona_name}:{Colors.RESET} {reply}")
                    else:
                        print()
                    _print_rel_change(rel_level)
                    last_reply[0] = ""
                    continue

                # 加入 CLI 去抖队列
                cli_message_queue.append(user_input)
                count = len(cli_message_queue)
                if count == 1:
                    print(f"  {Colors.DIM}⏳ 等待更多消息...（{debounce_seconds} 秒后发送）{Colors.RESET}", flush=True)
                else:
                    print(f"  {Colors.DIM}✓ 已收集 {count} 条消息，继续输入或等待发送{Colors.RESET}", flush=True)

            else:
                # 超时 — 检查是否有 CLI 消息需要发送
                if cli_message_queue:
                    count = len(cli_message_queue)
                    combined = "\n".join(cli_message_queue)
                    cli_message_queue = []
                    stats.message_count += count

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

                    reply, rel_level = await pipeline.process(
                        user_id, combined, "girlfriend_001",
                        on_token=_on_token,
                    )

                    if not spinner_stop.is_set():
                        spinner_stop.set()
                    spinner.cancel()
                    stats.end_level = rel_level

                    if first_token[0]:
                        print(f"\n{Colors.MAGENTA}{persona_name}:{Colors.RESET} {reply}")
                    else:
                        print()
                    _print_rel_change(rel_level)
                    last_reply[0] = ""

    except KeyboardInterrupt:
        pass
    finally:
        # 刷新所有去抖队列
        await debounce.flush_all()
        await manager.stop_all()

        # 退出总结
        stats.end_level = app.relationship_tracker.get_level(
            user_id, base_level=getattr(persona, 'relationship_level', 50),
            persona_id="girlfriend_001",
        )
        print(stats.summary(persona_name))
        logger.info("所有适配器已停止")

