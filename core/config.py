"""配置管理 — 加载 settings.json 中的高级参数"""

import json
from pathlib import Path

from loguru import logger

# 项目路径常量
ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"


def load_advanced() -> dict:
    """从 settings.json 读取高级参数，缺失项使用默认值"""
    path = CONFIG_DIR / "settings.json"
    defaults = {
        "segment_max_length": 50,
        "debounce_seconds": 3,
        "summarize_threshold": 15,
        "max_retries": 2,
        "max_messages": 50,
        "proactive_enabled": True,
        "proactive_morning": True,
        "proactive_evening": True,
        "proactive_missing_days": 2,
        "proactive_min_level": 20,
        "brain_enabled": True,
        "brain_max_tokens": 1000,
        "brain_debug": False,
    }
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            defaults.update(
                {k: v for k, v in data.get("advanced", {}).items() if k in defaults}
            )
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load settings.json, using defaults: {e}")
    return defaults
