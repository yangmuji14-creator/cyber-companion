"""Application factory — 组件初始化与依赖注入

将 main.py 的组件创建逻辑提取到此模块，使 main.py 只负责 CLI 入口。
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from core.config import ROOT, CONFIG_DIR, load_advanced, DEFAULT_PERSONA_ID
from core.llm import init_registry, LLMRegistry
from core.memory import MemoryManager, ChatHistoryStorage
from core.memory.open_loop import OpenLoopEngine
from core.memory.identity import IdentityLayer
from core.memory.life_summary import LifeSummaryEngine
from core.memory.embedder import SentenceTransformerEmbedder
from core.memory.vector_store import VectorStore
from core.persona import PersonaLoader
from core.personality import PersonalityEngine
from core.emotion import LLMEmotionAnalyzer
from core.proactive import ProactiveMessenger
from core.emotion.mood import MoodEngine
from core.social.affection.storage import UnifiedAffectionStorage
from core.social.affection.migration import migrate_from_legacy
from core.chat import ChatHandler
from core.brain import BrainCoordinator, BrainConfig
from core.tools.mcp_manager import MCPManager
from core.multimodal.vision import VisionManager


@dataclass
class AppComponents:
    """持有所有初始化后的组件"""
    registry: LLMRegistry
    memory_mgr: MemoryManager
    persona_loader: PersonaLoader
    personality_engine: PersonalityEngine
    chat_history: ChatHistoryStorage
    llm_emotion_analyzer: LLMEmotionAnalyzer
    mood_manager: MoodEngine
    proactive: ProactiveMessenger
    open_loop: OpenLoopEngine
    identity: IdentityLayer
    life_summary: LifeSummaryEngine
    unified_storage: UnifiedAffectionStorage
    handler: ChatHandler
    advanced_config: dict
    brain: BrainCoordinator | None = None
    mcp_manager: MCPManager | None = None
    vision_manager: VisionManager | None = None


class ComponentBuilder:
    """组件构建器 — 按领域分组创建逻辑"""

    def __init__(self, root: Path, config: dict):
        self.root = root
        self.config = config
        self._data_dir = str(root / "data")

    # ---- 存储层 ----

    def build_memory(self) -> tuple[MemoryManager, ChatHistoryStorage]:
        """创建记忆系统组件"""
        embedder = SentenceTransformerEmbedder()
        vector_store = VectorStore(str(self.root / "data" / "vectors.db"))
        memory_mgr = MemoryManager(
            self._data_dir, embedder=embedder, vector_store=vector_store,
        )
        chat_history = ChatHistoryStorage(
            self._data_dir, max_messages=self.config["max_messages"],
        )
        return memory_mgr, chat_history

    def build_unified_storage(self) -> UnifiedAffectionStorage:
        """创建亲密度统一存储，并迁移旧版数据"""
        storage = UnifiedAffectionStorage(self._data_dir)
        json_path = self.root / "data" / "relationships.json"
        if json_path.exists():
            try:
                migrated = migrate_from_legacy(storage, json_path)
                if migrated:
                    logger.info("旧版亲密度数据已迁移到统一存储")
            except Exception as e:
                logger.warning(f"亲密度数据迁移失败（将跳过）: {e}")
        return storage

    # ---- 行为层 ----

    def build_persona(self) -> PersonaLoader:
        return PersonaLoader(CONFIG_DIR / "personas.json")

    def build_personality(self) -> PersonalityEngine:
        return PersonalityEngine(self._data_dir)

    def build_emotion(self) -> tuple[LLMEmotionAnalyzer, MoodEngine]:
        return LLMEmotionAnalyzer(), MoodEngine(self._data_dir)

    def build_loop_components(self) -> tuple[OpenLoopEngine, IdentityLayer, LifeSummaryEngine]:
        return (
            OpenLoopEngine(self._data_dir),
            IdentityLayer(self._data_dir),
            LifeSummaryEngine(self._data_dir),
        )

    def build_proactive(self, persona_loader, memory_mgr, unified_storage, mood_manager) -> ProactiveMessenger:
        return ProactiveMessenger(
            persona_loader, memory_mgr, unified_storage,
            mood_engine=mood_manager,
            config=self.config,
        )

    # ---- 大脑模块 ----

    def build_brain(self, memory_mgr=None, persona_loader=None, mood_manager=None,
                    open_loop=None, identity=None, life_summary=None,
                    personality_engine=None, affection_storage=None,
                    chat_history=None) -> BrainCoordinator | None:
        """创建大脑模块（如果配置启用）

        将所有已初始化的子系统注入 BrainCoordinator，
        构建统一的内心独白生成入口。

        Args:
            memory_mgr: 记忆管理器
            persona_loader: 人设加载器
            mood_manager: 情绪管理器
            open_loop: 开放式循环引擎
            identity: 身份层
            life_summary: 人生总结引擎
            personality_engine: 人格引擎
            affection_storage: 亲密度存储
            chat_history: 聊天历史存储

        Returns:
            brain_enabled=True 时返回 BrainCoordinator，否则返回 None
        """
        if not self.config.get("brain_enabled", True):
            logger.info("Brain module is disabled via config")
            return None

        brain_config = BrainConfig(
            enabled=True,
            max_tokens=self.config.get("brain_max_tokens", 1000),
            debug=self.config.get("brain_debug", False),
            checker_enabled=self.config.get("checker_enabled", True),
        )

        # 从 persona_loader 获取人设名
        persona_name = "小雨"
        if persona_loader:
            try:
                persona = persona_loader.get(DEFAULT_PERSONA_ID)
                if persona and hasattr(persona, "name"):
                    persona_name = persona.name
            except Exception:
                pass

        coordinator = BrainCoordinator(
            config=brain_config,
            mood_engine=mood_manager,
            open_loop_engine=open_loop,
            chat_history=chat_history,
            personality_engine=personality_engine,
            affection_storage=affection_storage,
            identity=identity,
            life_summary=life_summary,
            persona_loader=persona_loader,
            memory_mgr=memory_mgr,
            persona_name=persona_name,
        )

        logger.info(
            f"Brain module initialized: max_tokens={brain_config.max_tokens}, "
            f"debug={brain_config.debug}"
        )
        return coordinator

    # ---- 组装 ----

    def build_all(self) -> AppComponents:
        """创建所有组件并组装"""
        registry = init_registry(CONFIG_DIR / "settings.json")
        memory_mgr, chat_history = self.build_memory()
        persona_loader = self.build_persona()
        personality_engine = self.build_personality()
        llm_emotion_analyzer, mood_manager = self.build_emotion()
        open_loop, identity, life_summary = self.build_loop_components()
        unified_storage = self.build_unified_storage()
        proactive = self.build_proactive(persona_loader, memory_mgr, unified_storage, mood_manager)

        # 注入 LLM 生成器到 ProactiveMessenger（用于主动消息的实时生成）
        if registry.available_models:
            _llm = registry.get()
            async def _generate(system_prompt: str, user_prompt: str,
                                max_tokens: int = 200, temperature: float = 0.95) -> str:
                response = await _llm.chat(
                    messages=[{"role": "user", "content": user_prompt}],
                    system_prompt=system_prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                return response.content
            proactive.set_llm_generator(_generate)

        # 大脑模块
        brain = self.build_brain(
            memory_mgr=memory_mgr,
            persona_loader=persona_loader,
            mood_manager=mood_manager,
            open_loop=open_loop,
            identity=identity,
            life_summary=life_summary,
            personality_engine=personality_engine,
            affection_storage=unified_storage,
            chat_history=chat_history,
        )

        # MCP Manager（同步创建，异步连接在 run_with_adapters 中）
        mcp_manager = MCPManager()

        # Vision Manager
        from core.config import load_vision_config
        llm = registry.get() if registry.available_models else None
        vision_manager = VisionManager(
            main_model=llm,
            vision_config=load_vision_config(),
        )

        handler = ChatHandler(
            registry=registry, memory_mgr=memory_mgr,
            persona_loader=persona_loader, personality_engine=personality_engine,
            chat_history=chat_history, llm_emotion_analyzer=llm_emotion_analyzer,
            proactive=proactive, mood_manager=mood_manager, config=self.config,
            open_loop=open_loop, identity=identity, life_summary=life_summary,
            affection_storage=unified_storage, brain=brain,
            mcp_manager=mcp_manager, vision_manager=vision_manager,
        )

        return AppComponents(
            registry=registry, memory_mgr=memory_mgr, persona_loader=persona_loader,
            personality_engine=personality_engine, chat_history=chat_history,
            llm_emotion_analyzer=llm_emotion_analyzer, mood_manager=mood_manager,
            proactive=proactive, open_loop=open_loop, identity=identity,
            life_summary=life_summary, unified_storage=unified_storage,
            handler=handler, advanced_config=self.config, brain=brain,
            mcp_manager=mcp_manager, vision_manager=vision_manager,
        )


def create_components(data_dir: str | Path | None = None) -> AppComponents:
    """创建并组装所有核心组件（便捷函数）

    Args:
        data_dir: 数据存储目录，默认 ROOT/data

    Returns:
        所有组件的容器
    """
    root = ROOT if data_dir is None else Path(data_dir)
    config = load_advanced()
    return ComponentBuilder(root, config).build_all()


from adapters.debounce import DebounceManager, DebounceState  # noqa: F401 — used in run_with_adapters


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
    from core.chat.display import (
        spinner_task, print_reply_token, print_rel_change,
        get_welcome_message, SessionStats,
    )

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
        """外部平台消息处理"""
        if message.platform == "cli":
            return ""

        # 图片消息：直接走 Vision Pipeline，不走去抖
        if message.metadata.get("is_image"):
            image_path = message.metadata.get("image_path", "")
            if image_path and app.vision_manager:
                try:
                    # 取得图片附文（用户发送图片时附带的话）
                    image_text = message.metadata.get("image_text", "") or ""
                    # 优化后的视觉识别 prompt：让视觉模型用聊天式的口语化描述
                    vision_prompt = (
                        "请用自然的口语描述这张图片的内容，像跟朋友聊天分享照片一样。"
                        "描述画面主题、氛围和有趣的细节，不要用「图片中」「图中显示」等书面语。"
                    )
                    vision_result = await app.vision_manager.process(
                        image_path, vision_prompt
                    )
                    if app.vision_manager.main_is_multimodal:
                        return vision_result
                    else:
                        # 降级模式：视觉描述 + 用户文字 → 主模型生成回复
                        enhanced = app.vision_manager.build_enhanced_message(
                            vision_result, image_text
                        )
                        reply, _ = await pipeline.process(
                            message.user_id, enhanced, DEFAULT_PERSONA_ID,
                        )
                        return reply
                except Exception as e:
                    logger.error(f"Vision processing failed: {e}")
                    return "图片识别失败了，请稍后再试~"
            return "收到图片了，但视觉识别还没配置~"

        # 普通消息：加入去抖队列
        await debounce.add_message(message.platform, message.user_id, message.content)
        return ""

    manager.set_message_handler(_handle_message)

    # 启动所有适配器
    await manager.start_all()

    # 连接 MCP Servers
    if app.mcp_manager:
        connected = await app.mcp_manager.load_and_connect(CONFIG_DIR)
        if connected > 0:
            logger.info(f"MCP: {connected} server(s) connected, "
                        f"{app.mcp_manager.tools_count} tools available")

    # ---- CLI 用户信息 ----
    user_id = "local_user"
    persona = app.persona_loader.get(DEFAULT_PERSONA_ID)
    persona_name = persona.name if persona else "小雨"

    # 会话统计
    stats = SessionStats()
    stats.start_level = int(app.unified_storage.get_level(
        user_id, persona_id=DEFAULT_PERSONA_ID,
    ))
    last_reply = [""]

    # CLI 斜杠命令处理器（本地处理，不走 pipeline）
    cli_commands = CommandHandler(app.handler)

    logger.info(f"多平台模式已启动: {platforms}")
    logger.info(f"模型: {app.registry.get().model_name}")
    logger.info(f"人设: {persona_name}")

    # 欢迎语
    welcome = get_welcome_message(persona, stats.start_level)
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
                            print_reply_token(persona_name, token, True)
                            first_token[0] = False
                        else:
                            print_reply_token(persona_name, token, False)

                    spinner = asyncio.create_task(
                        spinner_task(spinner_stop, persona_name)
                    )

                    reply, rel_level = await pipeline.process(
                        user_id, user_input, DEFAULT_PERSONA_ID,
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
                    print_rel_change(rel_level)
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
                            print_reply_token(persona_name, token, True)
                            first_token[0] = False
                        else:
                            print_reply_token(persona_name, token, False)

                    spinner = asyncio.create_task(
                        spinner_task(spinner_stop, persona_name)
                    )

                    reply, rel_level = await pipeline.process(
                        user_id, combined, DEFAULT_PERSONA_ID,
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
                    print_rel_change(rel_level)
                    last_reply[0] = ""

    except KeyboardInterrupt:
        pass
    finally:
        # 刷新所有去抖队列
        await debounce.flush_all()
        await manager.stop_all()

        # 退出总结
        stats.end_level = int(app.unified_storage.get_level(
            user_id, persona_id=DEFAULT_PERSONA_ID,
        ))
        print(stats.summary(persona_name))
        logger.info("所有适配器已停止")

