"""Application factory — 组件初始化与依赖注入

将 main.py 的组件创建逻辑提取到此模块，使 main.py 只负责 CLI 入口。
"""

from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from core.config import ROOT, CONFIG_DIR, load_advanced
from core.llm import init_registry, LLMRegistry
from core.memory import MemoryManager, ChatHistoryStorage
from core.memory.embedder import SentenceTransformerEmbedder
from core.memory.vector_store import VectorStore
from core.persona import PersonaLoader
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
    chat_history: ChatHistoryStorage
    llm_emotion_analyzer: LLMEmotionAnalyzer
    relationship_tracker: RelationshipTracker
    mood_manager: AIMoodManager
    proactive: ProactiveMessenger
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
    llm_emotion_analyzer = LLMEmotionAnalyzer()
    relationship_tracker = RelationshipTracker(str(root / "data"))
    chat_history = ChatHistoryStorage(
        str(root / "data"), max_messages=config["max_messages"]
    )
    mood_manager = AIMoodManager(str(root / "data"))

    proactive = ProactiveMessenger(
        persona_loader, memory_mgr, relationship_tracker,
        mood_manager=mood_manager,
        config=config,
    )

    handler = ChatHandler(
        registry=registry,
        memory_mgr=memory_mgr,
        persona_loader=persona_loader,
        chat_history=chat_history,
        llm_emotion_analyzer=llm_emotion_analyzer,
        relationship_tracker=relationship_tracker,
        proactive=proactive,
        mood_manager=mood_manager,
        config=config,
    )

    return AppComponents(
        registry=registry,
        memory_mgr=memory_mgr,
        persona_loader=persona_loader,
        chat_history=chat_history,
        llm_emotion_analyzer=llm_emotion_analyzer,
        relationship_tracker=relationship_tracker,
        mood_manager=mood_manager,
        proactive=proactive,
        handler=handler,
        advanced_config=config,
    )
