"""配置管理 — 加载 settings.json 中的高级参数"""

import json
from pathlib import Path

from loguru import logger

# 项目路径常量
ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"

# 默认人设 ID（统一管理，避免硬编码散布在各模块）
DEFAULT_PERSONA_ID = "girlfriend_001"


def load_advanced() -> dict:
    """从 settings.json 读取高级参数，缺失项使用默认值"""
    path = CONFIG_DIR / "settings.json"
    defaults = {
        "segment_max_length": 16,
        "debounce_seconds": 3,
        "summarize_threshold": 15,
        "max_retries": 2,
        "max_messages": 50,
        "proactive_enabled": True,
        "proactive_active_start": 7,
        "proactive_active_end": 23,
        "proactive_interval_min": 30,
        "proactive_interval_max": 180,
        "proactive_missing_days": 2,
        "proactive_min_level": 20,
        "auto_extract_memory": False,
        "brain_enabled": True,
        "brain_max_tokens": 1000,
        "brain_debug": False,
        "checker_enabled": True,
        "vision_model": {
            "provider": "openai",
            "model_name": "",
            "api_key": "",
            "base_url": "",
        },
    }
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            defaults.update(
                {k: v for k, v in data.get("advanced", {}).items() if k in defaults}
            )
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load settings.json, using defaults: {e}")
    return defaults


def load_vision_config() -> dict:
    """加载视觉模型配置（settings.json → advanced → vision_model）"""
    advanced = load_advanced()
    return advanced.get("vision_model", {})


def load_mcp_config() -> list[dict]:
    """加载 MCP Servers 配置"""
    path = CONFIG_DIR / "mcp_servers.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("servers", [])
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to load mcp_servers.json: {e}")
        return []
