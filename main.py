"""Cyber Girlfriend — 赛博女友（纯 CMD 聊天）

集成情绪状态机、人格引擎、工具调用、向量记忆等完整功能。

运行方式：
    python main.py setup   — 首次运行设置向导
    python main.py         — 直接进聊天
"""

import asyncio
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
from loguru import logger

load_dotenv()

from core.config import ROOT, CONFIG_DIR, DATA_DIR, load_advanced

# 日志
logger.remove()
logger.add(sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{level:8}</level> | {message}")
logger.add("logs/app.log", rotation="10 MB", retention="7 days", level="DEBUG")

ADVANCED = load_advanced()


# ========== 核心组件初始化 ==========

from core.llm import init_registry
from core.memory import MemoryManager, ChatHistoryStorage
from core.memory.embedder import SentenceTransformerEmbedder
from core.memory.vector_store import VectorStore
from core.persona import PersonaLoader
from core.emotion import EmotionAnalyzer, LLMEmotionAnalyzer, MoodEngine
from core.relationship import RelationshipTracker
from core.proactive import ProactiveMessenger
from core.personality import PersonalityEngine
from core.tools import ToolRegistry, TimeTool, CalculatorTool, WeatherTool
from core.chat import ChatHandler

registry = init_registry(CONFIG_DIR / "settings.json")

# 向量记忆：嵌入器不可用时自动降级为关键词搜索
embedder = SentenceTransformerEmbedder()
vector_store = VectorStore(str(ROOT / "data" / "vectors.db"))
memory_mgr = MemoryManager(
    str(ROOT / "data"),
    embedder=embedder,
    vector_store=vector_store,
)
persona_loader = PersonaLoader(CONFIG_DIR / "personas.json")
emotion_analyzer = EmotionAnalyzer()
llm_emotion_analyzer = LLMEmotionAnalyzer()
relationship_tracker = RelationshipTracker(str(ROOT / "data"))
chat_history = ChatHistoryStorage(str(ROOT / "data"), max_messages=ADVANCED["max_messages"])
proactive = ProactiveMessenger(
    persona_loader, memory_mgr, relationship_tracker,
    config=ADVANCED,
)

# ---- 新增模块初始化 ----

# 情绪状态机
mood_engine = MoodEngine(str(ROOT / "data"))

# 人格引擎
personality_engine = PersonalityEngine(str(ROOT / "data"))

# 工具注册
tool_registry = ToolRegistry()
tool_registry.register(TimeTool())
tool_registry.register(CalculatorTool())
tool_registry.register(WeatherTool())

handler = ChatHandler(
    registry=registry,
    memory_mgr=memory_mgr,
    persona_loader=persona_loader,
    chat_history=chat_history,
    llm_emotion_analyzer=llm_emotion_analyzer,
    relationship_tracker=relationship_tracker,
    proactive=proactive,
    mood_engine=mood_engine,
    personality_engine=personality_engine,
    tool_registry=tool_registry,
    config=ADVANCED,
)


# ========== 命令行入口 ==========

def main():
    import argparse

    parser = argparse.ArgumentParser(description="🎀 Cyber Girlfriend")
    parser.add_argument(
        "command", nargs="?", default="run",
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
        asyncio.run(handler.run())
    except KeyboardInterrupt:
        print()
        logger.info("拜拜~")


if __name__ == "__main__":
    main()
