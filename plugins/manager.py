"""Plugin Manager — 插件管理器

管理插件的加载、注册、执行。
"""

import importlib
import sys
from pathlib import Path
from typing import Any

from loguru import logger

from .base import Plugin, PluginContext, PluginResult


class PluginManager:
    """插件管理器"""

    def __init__(self, plugins_dir: str = ""):
        self._plugins_dir = Path(plugins_dir) if plugins_dir else Path(__file__).parent
        self._plugins: dict[str, Plugin] = {}
        self._load_order: list[str] = []

    def register(self, plugin: Plugin) -> None:
        """注册一个插件实例"""
        if not plugin.name:
            raise ValueError("Plugin must have a name")

        if plugin.name in self._plugins:
            logger.warning(f"Plugin '{plugin.name}' already registered, replacing")

        self._plugins[plugin.name] = plugin
        if plugin.name not in self._load_order:
            self._load_order.append(plugin.name)

        logger.info(f"Registered plugin: {plugin.name} v{plugin.version}")

    def unregister(self, name: str) -> bool:
        """注销插件"""
        if name in self._plugins:
            del self._plugins[name]
            self._load_order.remove(name)
            logger.info(f"Unregistered plugin: {name}")
            return True
        return False

    def get(self, name: str) -> Plugin | None:
        """获取插件"""
        return self._plugins.get(name)

    def list_plugins(self) -> list[Plugin]:
        """列出所有插件（按优先级排序）"""
        plugins = [self._plugins[name] for name in self._load_order if name in self._plugins]
        return sorted(plugins, key=lambda p: p.priority, reverse=True)

    def list_enabled(self) -> list[Plugin]:
        """列出所有启用的插件"""
        return [p for p in self.list_plugins() if p.enabled]

    async def process_message(self, context: PluginContext) -> list[PluginResult]:
        """处理消息：按优先级依次调用所有插件

        Returns:
            所有插件的结果列表
        """
        results = []

        for plugin in self.list_enabled():
            try:
                result = await plugin.on_message(context)
                if result is not None:
                    results.append(result)
                    if result.consume_message:
                        break  # 消费消息，不再传递
            except Exception as e:
                logger.error(f"Plugin {plugin.name} failed: {e}")

        return results

    async def process_reply(self, context: PluginContext, reply: str) -> str:
        """处理回复：让所有插件有机会修改回复"""
        current_reply = reply

        for plugin in self.list_enabled():
            try:
                current_reply = await plugin.on_reply(context, current_reply)
            except Exception as e:
                logger.error(f"Plugin {plugin.name} reply hook failed: {e}")

        return current_reply

    async def on_session_start(self, user_id: str, persona_id: str) -> None:
        """会话开始通知所有插件"""
        for plugin in self.list_enabled():
            try:
                await plugin.on_session_start(user_id, persona_id)
            except Exception as e:
                logger.error(f"Plugin {plugin.name} session start failed: {e}")

    async def on_session_end(self, user_id: str, persona_id: str) -> None:
        """会话结束通知所有插件"""
        for plugin in self.list_enabled():
            try:
                await plugin.on_session_end(user_id, persona_id)
            except Exception as e:
                logger.error(f"Plugin {plugin.name} session end failed: {e}")

    def get_all_commands(self) -> dict[str, tuple[str, Plugin]]:
        """获取所有插件提供的命令

        Returns:
            {"/command": ("description", plugin)}
        """
        commands = {}
        for plugin in self.list_enabled():
            for cmd, desc in plugin.get_commands().items():
                commands[cmd] = (desc, plugin)
        return commands

    async def handle_command(self, command: str, args: str, context: PluginContext) -> PluginResult | None:
        """处理插件命令"""
        commands = self.get_all_commands()
        if command in commands:
            _, plugin = commands[command]
            return await plugin.handle_command(command, args, context)
        return None

    def load_from_directory(self, directory: str | Path | None = None) -> int:
        """从目录加载插件

        扫描目录下的 Python 文件，寻找 Plugin 子类并实例化。
        """
        dir_path = Path(directory) if directory else self._plugins_dir
        if not dir_path.exists():
            return 0

        loaded = 0
        for py_file in dir_path.glob("*.py"):
            if py_file.name.startswith("_"):
                continue

            try:
                module_name = f"plugins.{py_file.stem}"
                if module_name in sys.modules:
                    module = sys.modules[module_name]
                else:
                    module = importlib.import_module(module_name)

                # 寻找 Plugin 子类
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (isinstance(attr, type) and
                        issubclass(attr, Plugin) and
                        attr is not Plugin):
                        plugin_instance = attr()
                        self.register(plugin_instance)
                        loaded += 1
            except Exception as e:
                logger.warning(f"Failed to load plugin from {py_file}: {e}")

        return loaded

    def get_info(self) -> list[dict[str, Any]]:
        """获取所有插件信息"""
        return [p.get_info() for p in self.list_plugins()]
