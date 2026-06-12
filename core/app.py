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
from core.state import AIMoodManager
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
    mood_manager: AIMoodManager
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
    mood_manager = AIMoodManager(str(root / "data"))

    # v1.2/v1.3 新增组件
    open_loop = OpenLoopEngine(str(root / "data"))
    identity = IdentityLayer(str(root / "data"))
    life_summary = LifeSummaryEngine(str(root / "data"))

    proactive = ProactiveMessenger(
        persona_loader, memory_mgr, relationship_tracker,
        mood_manager=mood_manager,
        open_loop=open_loop,
        identity=identity,
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


async def run_with_adapters(app: AppComponents, platforms: list[str]) -> None:
    """启动多平台适配器模式

    同时运行 CLI 聊天和指定平台适配器。
    """
    from adapters import AdapterManager
    from adapters.cli import CLIAdapter
    from adapters.wechat import WeChatAdapter
    from adapters.api import APIAdapter
    from adapters.base import AdapterConfig

    manager = AdapterManager()

    # 注册 CLI（始终启用）
    cli = CLIAdapter()
    manager.register(cli)

    # 注册指定平台
    for platform in platforms:
        if platform == "wechat":
            manager.register(WeChatAdapter())
        elif platform == "api":
            manager.register(APIAdapter())

    # 设置消息处理回调
    async def _handle_message(message):
        """处理来自任何平台的消息"""
        from core.chat.pipeline import ChatPipeline
        from core.tools import ToolRegistry
        from core.tools.builtin import register_all
        from core.dialogue.thinker import DialogueThinker
        from core.dialogue.consistency import ConsistencyGuard
        from core.dialogue.topic_tracker import TopicTracker

        user_id = message.user_id
        content = message.content
        persona_id = "girlfriend_001"

        # 获取 LLM
        llm = None
        if app.registry.available_models:
            try:
                llm = app.registry.get()
            except Exception:
                pass

        # 构建 pipeline
        dialogue_thinker = DialogueThinker()
        consistency_guard = ConsistencyGuard()
        topic_tracker = TopicTracker()
        tool_registry = ToolRegistry()
        register_all(tool_registry, data_dir=str(app.mood_manager.base_data_dir))

        pipeline = ChatPipeline(
            llm, app.memory_mgr, app.persona_loader, app.personality_engine,
            app.chat_history, app.llm_emotion_analyzer, app.relationship_tracker,
            app.mood_manager, app.advanced_config,
            dialogue_thinker=dialogue_thinker,
            consistency_guard=consistency_guard,
            topic_tracker=topic_tracker,
            tool_registry=tool_registry,
            open_loop=app.open_loop,
            identity=app.identity,
            life_summary=app.life_summary,
        )

        reply, _ = await pipeline.process(user_id, content, persona_id)
        return reply

    manager.set_message_handler(_handle_message)

    # 启动所有适配器
    await manager.start_all()

    logger.info(f"多平台模式已启动: {platforms}")
    logger.info("按 Ctrl+C 退出")

    try:
        # 主循环：轮询 CLI 输入 + 主动消息
        while True:
            # 尝试读取 CLI 输入（非阻塞）
            user_input = await cli.get_input(timeout=1.0)
            if user_input is not None:
                if user_input.strip().lower() in ("/quit", "quit"):
                    logger.info("用户请求退出")
                    break
                message = cli.create_message("local_user", user_input)
                reply = await _handle_message(message)
                await cli.send("local_user", reply)
            else:
                # 超时 — 检查主动消息（由 scheduler 触发）
                pass
    except KeyboardInterrupt:
        pass
    finally:
        await manager.stop_all()
        logger.info("所有适配器已停止")

