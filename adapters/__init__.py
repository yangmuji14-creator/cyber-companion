"""Adapters — 平台接入层

支持多平台接入：
- CLI: 命令行界面（当前已有）
- WebUI: Web 界面
- WeChat: 微信
- QQ: QQ
- Telegram: Telegram
- Discord: Discord
- API: REST API

适配器接口：
- BaseAdapter: 适配器基类
- AdapterManager: 适配器管理器
"""

from .base import BaseAdapter, AdapterMessage, AdapterConfig
from .manager import AdapterManager

__all__ = ["BaseAdapter", "AdapterMessage", "AdapterConfig", "AdapterManager"]
