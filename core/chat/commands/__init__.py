"""commands 包 — 斜杠命令系统

向后兼容导出：
  CommandHandler — 斜杠命令路由和执行器
  Colors         — ANSI 颜色码
  COMMANDS       — 命令注册表
"""

from core.chat.commands.handler import CommandHandler
from core.chat.commands.colors import Colors
from core.chat.commands.registry import COMMANDS

__all__ = [
    "CommandHandler",
    "Colors",
    "COMMANDS",
]
