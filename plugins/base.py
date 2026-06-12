"""Plugin Base — 插件基类

所有插件必须继承 Plugin 并实现必要方法。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from loguru import logger


@dataclass
class PluginContext:
    """插件上下文：传递给插件的运行时信息"""
    user_id: str
    persona_id: str
    message: str
    emotion: str = ""
    relationship_level: int = 50
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PluginResult:
    """插件执行结果"""
    success: bool
    response: str = ""           # 插件回复（会注入到对话）
    action: str = ""             # 动作类型：reply, modify, trigger
    data: dict[str, Any] = field(default_factory=dict)  # 额外数据
    consume_message: bool = True  # 是否消费原始消息（不再传递给其他插件）


class Plugin(ABC):
    """插件基类"""

    name: str = ""
    description: str = ""
    version: str = "1.0.0"
    author: str = ""

    # 插件配置
    enabled: bool = True
    priority: int = 0  # 优先级，数字越大越先执行

    def __init__(self):
        self._logger = logger.bind(plugin=self.name)

    @abstractmethod
    async def on_message(self, context: PluginContext) -> PluginResult | None:
        """处理用户消息

        Args:
            context: 插件上下文

        Returns:
            PluginResult 或 None（不处理）
        """
        pass

    async def on_reply(self, context: PluginContext, reply: str) -> str:
        """处理 AI 回复（可修改）

        Args:
            context: 插件上下文
            reply: AI 原始回复

        Returns:
            修改后的回复
        """
        return reply

    async def on_session_start(self, user_id: str, persona_id: str) -> None:
        """会话开始时调用"""
        pass

    async def on_session_end(self, user_id: str, persona_id: str) -> None:
        """会话结束时调用"""
        pass

    def get_commands(self) -> dict[str, str]:
        """返回插件提供的斜杠命令

        Returns:
            {"/command": "description"}
        """
        return {}

    async def handle_command(self, command: str, args: str, context: PluginContext) -> PluginResult:
        """处理插件命令"""
        return PluginResult(success=False, response="命令未实现")

    def get_info(self) -> dict[str, Any]:
        """获取插件信息"""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "enabled": self.enabled,
            "priority": self.priority,
        }
