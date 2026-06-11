"""chat — 聊天交互层

ChatPipeline:   消息处理管线（情绪→记忆→Prompt→LLM→保存→后台）
CommandHandler: 斜杠命令路由和执行
ChatHandler:    终端聊天循环管理
"""

from core.chat.pipeline import ChatPipeline, format_multi_message, get_time_context, timestamp, get_llm_error_message
from core.chat.commands import CommandHandler, Colors, COMMANDS
from core.chat.handler import ChatHandler, SessionStats

__all__ = [
    "ChatPipeline", "ChatHandler", "CommandHandler", "SessionStats",
    "format_multi_message", "get_time_context", "timestamp", "get_llm_error_message",
    "Colors", "COMMANDS",
]
