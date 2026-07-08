"""Integration connectivity test — 架构重构后跨模块连通性验证"""

import asyncio
import sys
import shutil
import tempfile
from pathlib import Path

import pytest


# ── 第1层：核心配置与 LLM ──

def test_config_imports():
    from core.config import ROOT, CONFIG_DIR, DATA_DIR, DEFAULT_PERSONA_ID, load_advanced
    assert isinstance(ROOT, Path)
    assert ROOT.exists()
    assert DEFAULT_PERSONA_ID == "girlfriend_001"


def test_llm_registry_imports():
    from core.llm import BaseLLM, LLMResponse, LLMRegistry, get_llm, init_registry
    from core.llm.openai_compatible import OpenAICompatibleLLM
    from core.llm.deepseek import DeepSeekLLM
    assert BaseLLM is not None
    assert OpenAICompatibleLLM is not None


# ── 第2层：记忆与存储模块 ──

def test_memory_module_imports():
    """去重后核心记忆导入"""
    from core.memory import MemoryManager, ChatHistoryStorage, MemorySummarizer
    from core.memory.identity import IdentityLayer, IdentityProfile, IdentityStorage
    from core.memory.open_loop import OpenLoopEngine, OpenLoop, OpenLoopStorage
    from core.memory.life_summary import LifeSummaryEngine, LifeSummary, LifeSummaryStorage
    assert MemoryManager is not None
    assert IdentityLayer is not None
    assert IdentityStorage is not None
    assert OpenLoopEngine is not None
    assert LifeSummaryEngine is not None


def test_old_modules_deleted():
    """旧路径已删除"""
    with pytest.raises(ImportError):
        import core.identity  # noqa
    with pytest.raises(ImportError):
        import core.open_loop  # noqa
    with pytest.raises(ImportError):
        import core.summary  # noqa


def test_vector_memory_imports():
    from core.memory.embedder import SentenceTransformerEmbedder
    from core.memory.vector_store import VectorStore
    from core.memory.layers.working_memory import WorkingMemory
    from core.memory.layers.short_term import ShortTermMemory
    from core.memory.layers.long_term import LongTermMemory
    from core.memory.layers.manager import MultiLayerMemoryManager
    assert SentenceTransformerEmbedder is not None


# ── 第3层：聊天管道 — 含拆分后的子模块 ──

def test_chat_pipeline_imports():
    from core.chat.pipeline import ChatPipeline, format_multi_message, get_time_context
    from core.chat.tool_handler import parse_tool_call, build_tools_prompt, call_llm_with_tools
    from core.chat.post_process import PostProcessOrchestrator
    from core.chat.display import spinner_task, print_reply_token, get_welcome_message, SessionStats
    assert ChatPipeline is not None
    assert PostProcessOrchestrator is not None
    assert callable(format_multi_message)


def test_chat_handler_imports():
    from core.chat.handler import ChatHandler
    from core.chat.commands import CommandHandler, Colors
    assert ChatHandler is not None
    assert CommandHandler is not None


# ── 第4层：人格、情绪、社交 ──

def test_persona_personality_imports():
    from core.persona import PersonaLoader, PromptBuilder
    from core.persona.drift_monitor import PersonaDriftMonitor
    from core.personality import PersonalityEngine
    assert PersonaLoader is not None


def test_emotion_module_imports():
    from core.emotion import EmotionEnhancer, MessageSegmenter, MoodExpressionEngine
    from core.emotion.analyzer import EmotionAnalyzer
    from core.emotion.llm_analyzer import LLMEmotionAnalyzer
    from core.emotion.mood import MoodEngine, MoodState
    assert LLMEmotionAnalyzer is not None


def test_social_module_imports():
    from core.social.affection.storage import UnifiedAffectionStorage
    from core.social.affection.migration import migrate_from_legacy
    from core.social.relationship.evolution import RelationshipEvolution
    from core.social.relationship.events import RelationshipEventTracker
    assert UnifiedAffectionStorage is not None


# ── 第5层：大脑模块 ──

def test_brain_module_imports():
    from core.brain import BrainCoordinator, BrainConfig
    from core.brain.collector import StateCollector
    from core.brain.organizer import ThoughtOrganizer
    from core.brain.weaver import MonologueWeaver
    from core.brain.triggers import MemoryTrigger
    from core.brain.checker import CharacterBreakDetector
    assert BrainCoordinator is not None
    assert StateCollector is not None


# ── 第6层：对话与多模态 ──

def test_dialogue_module_imports():
    from core.dialogue import DialogueThinker, PersonaConsistencyChecker, ConsistencyGuard
    from core.dialogue.topic_tracker import TopicTracker
    assert DialogueThinker is not None


def test_multimodal_module_imports():
    from core.multimodal import StickerReplier
    from core.multimodal.image_handler import ImageHandler
    assert StickerReplier is not None


# ── 第7层：适配器与去抖 ──

def test_adapters_imports():
    from adapters.base import BaseAdapter, AdapterConfig, AdapterMessage
    from adapters.manager import AdapterManager
    from adapters.cli import CLIAdapter
    from adapters.debounce import DebounceManager, DebounceState
    assert AdapterManager is not None
    assert CLIAdapter is not None
    assert DebounceManager is not None


# ── 第8层：组件组装 ──

def test_component_builder_imports():
    from core.app import AppComponents, ComponentBuilder, create_components
    assert AppComponents is not None
    assert callable(create_components)


# ── 第9层：工具模块 ──

def test_tools_imports():
    from core.tools import ToolRegistry
    from core.tools.base import BaseTool
    from core.tools.weather import WeatherTool
    from core.tools.calculator import CalculatorTool
    from core.tools.time_tool import TimeTool
    assert ToolRegistry is not None
    assert BaseTool is not None


# ── 第10层：跨模块实例化与互连 ──

@pytest.mark.asyncio
async def test_memory_layer_instantiation():
    """验证记忆层实例化互相独立"""
    tmpdir = Path(tempfile.mkdtemp())
    try:
        from core.memory.identity import IdentityLayer
        from core.memory.open_loop import OpenLoopEngine
        from core.memory.life_summary import LifeSummaryEngine
        from core.memory.chat_history import ChatHistoryStorage

        identity = IdentityLayer(tmpdir)
        profile = identity.load("test_user")
        assert profile.user_id == "test_user"
        identity.extract_from_message("test_user", "我是学计算机的")
        ctx = identity.get_context("test_user")
        assert isinstance(ctx, str)

        open_loop = OpenLoopEngine(tmpdir)
        loops = open_loop.detect("test_user", "明天要考试了")
        assert isinstance(loops, list)

        life_summary = LifeSummaryEngine(tmpdir)
        ls = life_summary.load("test_user")
        assert ls.user_id == "test_user"

        chat = ChatHistoryStorage(str(tmpdir), max_messages=50)
        chat.add_message("test_user", "user", "你好")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_adapter_debounce_connectivity():
    from adapters.debounce import DebounceManager, DebounceState
    from adapters.manager import AdapterManager
    from adapters.cli import CLIAdapter

    manager = AdapterManager()
    cli = CLIAdapter()
    manager.register(cli)
    assert manager.get("cli") is not None


def test_session_stats_connectivity():
    from core.chat.display import SessionStats
    stats = SessionStats()
    stats.message_count = 10
    stats.start_level = 50
    stats.end_level = 55
    summary = stats.summary("小雨")
    assert "10" in summary
    assert "+5" in summary


def test_pipeline_tool_handler_connectivity():
    from core.chat.tool_handler import parse_tool_call, build_tools_prompt

    result = parse_tool_call('【工具调用：weather(city="北京")】')
    assert len(result) == 1
    assert result[0][0] == "weather"
    assert result[0][1].get("city") == "北京"

    result = parse_tool_call("今天天气怎么样？")
    assert len(result) == 0


def test_post_process_orchestrator_connectivity():
    from core.chat.post_process import PostProcessOrchestrator

    class MockPipeline:
        _memory_mgr = None
        _life_summary = None
        _relationship_events = None
        _drift_monitor = None
        _last_replies = {}
        _last_drift_check = {}
        _conversation_counter = {}

    orch = PostProcessOrchestrator(MockPipeline())
    assert orch is not None


def test_chat_display_functions():
    from core.chat.display import get_welcome_message, SPINNER_FRAMES, SPINNER_TEXT

    class MockPersona:
        pass

    msg = get_welcome_message(MockPersona(), 80)
    assert isinstance(msg, str) and len(msg) > 0
    assert len(SPINNER_FRAMES) == 10
    assert "思考" in SPINNER_TEXT


# ── 终验：全量导入链路 ──

def test_full_cross_module_import_chain():
    """复现 main.py 完整导入链路"""
    from core.config import ROOT, CONFIG_DIR, DATA_DIR, load_advanced, DEFAULT_PERSONA_ID
    from core.app import AppComponents, create_components, ComponentBuilder
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
    from core.chat import ChatHandler, ChatPipeline, CommandHandler
    from core.brain import BrainCoordinator, BrainConfig
    from adapters import AdapterManager
    from adapters.debounce import DebounceManager, DebounceState

    assert ChatPipeline is not None
    assert AppComponents is not None
    assert BrainCoordinator is not None
    assert DebounceManager is not None
