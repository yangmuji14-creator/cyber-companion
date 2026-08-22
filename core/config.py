"""配置管理 — 加载 settings.json 中的高级参数"""

import json
import os
import hashlib
from pathlib import Path

from loguru import logger
from core.runtime.paths import bootstrap_example_config, ensure_user_directories, resolve_runtime_paths

# Runtime paths are source-checkout compatible and become portable when the
# launcher sets CC_PORTABLE=1. Modules should use these constants instead of
# deriving paths from __file__.
_RUNTIME_PATHS = resolve_runtime_paths()
ROOT = _RUNTIME_PATHS.home_dir
RESOURCE_DIR = _RUNTIME_PATHS.resource_dir
CONFIG_DIR = _RUNTIME_PATHS.config_dir
DATA_DIR = _RUNTIME_PATHS.data_dir
LOGS_DIR = _RUNTIME_PATHS.logs_dir
CACHE_DIR = _RUNTIME_PATHS.cache_dir
if _RUNTIME_PATHS.portable:
    bootstrap_example_config(_RUNTIME_PATHS)
    ensure_user_directories(_RUNTIME_PATHS)

# 默认人设 ID（统一管理，避免硬编码散布在各模块）
DEFAULT_PERSONA_ID = "girlfriend_001"


def normalize_wechat_accounts(wechat_config: object) -> list[dict]:
    """Return a copy of WeChat account config in the current array format.

    ``persona_id`` became account-scoped after the original multi-contact
    binding model. Older installations therefore receive the default persona
    without requiring an eager settings rewrite.
    """
    accounts: list[object]
    if isinstance(wechat_config, dict):
        configured = wechat_config.get("accounts")
        if isinstance(configured, list):
            accounts = configured
        elif wechat_config:
            accounts = [{
                "id": "default",
                "enabled": wechat_config.get("enabled", True),
                "auto_start": wechat_config.get("auto_start", True),
                "persona_id": wechat_config.get("persona_id", DEFAULT_PERSONA_ID),
            }]
        else:
            accounts = []
    elif isinstance(wechat_config, list):
        accounts = wechat_config
    else:
        accounts = []

    normalized: list[dict] = []
    for raw in accounts:
        if not isinstance(raw, dict):
            continue
        account = dict(raw)
        account["id"] = str(account.get("id") or "default").strip()
        account["enabled"] = bool(account.get("enabled", True))
        account["auto_start"] = bool(account.get("auto_start", True))
        account["persona_id"] = (
            str(account.get("persona_id") or DEFAULT_PERSONA_ID).strip()
            or DEFAULT_PERSONA_ID
        )
        normalized.append(account)
    return normalized


def resolve_wechat_account_persona(
    advanced_config: dict,
    account_id: str,
) -> str | None:
    """Resolve the role selected for a configured WeChat account.

    ``None`` means the account is not present in config. Callers may then keep
    a legacy contact binding instead of unexpectedly resetting it.
    """
    adapters = advanced_config.get("adapters", {}) if isinstance(advanced_config, dict) else {}
    wechat = adapters.get("wechat", {}) if isinstance(adapters, dict) else {}
    for account in normalize_wechat_accounts(wechat):
        if account["id"] == account_id:
            return account["persona_id"]
    return None


def load_advanced() -> dict:
    """从 settings.json 读取高级参数，缺失项使用默认值"""
    path = CONFIG_DIR / "settings.json"
    defaults = {
        "segment_max_length": 16,
        "debounce_seconds": 3,
        "summarize_threshold": 15,
        "max_retries": 2,
        "max_messages": 50,
        "context_char_budget": 24000,
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
        # 适配器多账号配置（T4）：advanced.adapters.<platform>.accounts = [{id, enabled, auto_start}, ...]
        "adapters": {},
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
    from core.security import get_secret_manager, resolve_config_secret

    advanced = load_advanced()
    config = dict(advanced.get("vision_model", {}) or {})
    config["api_key"] = resolve_config_secret(
        config,
        env_value=os.getenv("OPENAI_API_KEY", ""),
        manager=get_secret_manager(CONFIG_DIR),
    )
    return config


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


# ---------------------------------------------------------------------------
# 复合 user_id 方案（T5）
#
# 内存层用双冒号 `::` 分隔，便于 parse_uid 解析；磁盘层用子目录结构
# （见 ChatHistoryStorage._get_user_file），规避 Windows 文件名禁止冒号的问题。
#
# 格式：
#   wechat::{account_id}::{wxid}   — 微信用户（多账号隔离）
#   web::{persona_id}              — WebUI 用户（按人设隔离）
#   cli::local                     — CLI 用户（单例）
#   api::{user_id}                 — HTTP API 用户
#
# 旧格式（无 `::`）走 legacy 路径，向后兼容现有数据。
# ---------------------------------------------------------------------------
USER_ID_SCHEME = "v2"
SEP = "::"


def build_wechat_uid(account_id: str, wxid: str) -> str:
    """构造微信复合 user_id：`wechat::{account_id}::{wxid}`"""
    return f"wechat{SEP}{account_id}{SEP}{wxid}"


def build_web_uid(persona_id: str) -> str:
    """构造 WebUI 复合 user_id：`web::{persona_id}`"""
    return f"web{SEP}{persona_id}"


def build_cli_uid() -> str:
    """构造 CLI 复合 user_id：`cli::local`"""
    return f"cli{SEP}local"


def build_api_uid(user_id: str) -> str:
    """构造 HTTP API 复合 user_id：`api::{user_id}`"""
    return f"api{SEP}{user_id}"


def build_memory_scope_uid(
    user_id: str,
    persona_id: str,
    conversation_id: str | None = None,
) -> str:
    """Build a stable storage namespace for one bound conversation/persona.

    ``user_id`` identifies the external peer (for example a WeChat contact),
    while ``persona_id`` and ``conversation_id`` identify the role binding that
    owns the memory.  The digest keeps the value safe for every supported
    filesystem and avoids leaking wxids or conversation ids into filenames.
    """
    payload = "\x00".join((str(user_id or ""), str(persona_id or ""), str(conversation_id or "")))
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
    return f"scope_{digest}"


def parse_uid(uid: str) -> dict:
    """解析复合 user_id。

    Returns:
        {"platform", "account_id", "persona_id", "raw_id"}

    malformed uid 不抛异常，返回 ``platform="unknown"`` 并保留原值为 ``raw_id``，
    调用方据此走 legacy 兼容路径。
    """
    parts = uid.split(SEP)
    if len(parts) == 3 and parts[0] == "wechat":
        return {
            "platform": "wechat",
            "account_id": parts[1],
            "persona_id": "",
            "raw_id": parts[2],
        }
    if len(parts) == 2 and parts[0] == "web":
        return {
            "platform": "web",
            "account_id": "",
            "persona_id": parts[1],
            "raw_id": parts[1],
        }
    if len(parts) == 2 and parts[0] == "cli":
        return {
            "platform": "cli",
            "account_id": "",
            "persona_id": "",
            "raw_id": parts[1],
        }
    if len(parts) == 2 and parts[0] == "api":
        return {
            "platform": "api",
            "account_id": "",
            "persona_id": "",
            "raw_id": parts[1],
        }
    return {
        "platform": "unknown",
        "account_id": "",
        "persona_id": "",
        "raw_id": uid,
    }
