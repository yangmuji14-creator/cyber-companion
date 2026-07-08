"""chat — 聊天交互层

ChatPipeline:   消息处理管线（情绪→记忆→Prompt→LLM→保存→后台）
CommandHandler: 斜杠命令路由和执行
ChatHandler:    终端聊天循环管理
Display:        终端输出工具（spinner、流式、分段打印、统计）
"""

from core.chat.pipeline import ChatPipeline, format_multi_message, get_time_context, timestamp, get_llm_error_message
from core.chat.commands import CommandHandler, Colors, COMMANDS
from core.chat.handler import ChatHandler
from core.chat.display import SessionStats, spinner_task, print_reply_token, get_welcome_message

__all__ = [
    "ChatPipeline", "ChatHandler", "CommandHandler", "SessionStats",
    "format_multi_message", "get_time_context", "timestamp", "get_llm_error_message",
    "Colors", "COMMANDS",
    "spinner_task", "print_reply_token", "get_welcome_message",
]
