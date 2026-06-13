"""Plugin System — 插件系统

允许第三方扩展：
- 游戏插件
- 角色插件
- 工具插件
- MCP 插件

插件结构：
- Plugin: 插件基类
- PluginManager: 插件管理器
"""

from .base import Plugin, PluginContext, PluginResult
from .manager import PluginManager

__all__ = ["Plugin", "PluginContext", "PluginResult", "PluginManager"]
