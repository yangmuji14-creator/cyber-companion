"""Local, privacy-preserving application diagnostics."""

from __future__ import annotations

import json
import os
import platform
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

_SENSITIVE_PARTS = ("api_key", "password", "secret", "token", "credential", "authorization")


def _check(check_id: str, label: str, status: str, message: str, **details) -> dict:
    item = {"id": check_id, "label": label, "status": status, "message": message}
    if details:
        item["details"] = details
    return item


def _directory_check(check_id: str, label: str, directory: Path) -> dict:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=directory, prefix=".diagnostic-", delete=True):
            pass
        return _check(check_id, label, "ok", "可以正常读写")
    except OSError as exc:
        return _check(check_id, label, "error", "无法写入，请检查目录权限", error=type(exc).__name__)


def _database_check(database: Path) -> dict:
    if not database.exists():
        return _check("database", "本地数据库", "warn", "尚未创建，将在首次使用时自动生成")
    try:
        uri = f"file:{database.as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=5) as connection:
            integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if integrity.lower() != "ok":
            return _check("database", "本地数据库", "error", "完整性检查失败", result=integrity)
        return _check("database", "本地数据库", "ok", f"完整性正常，结构版本 {version}", version=version)
    except (sqlite3.Error, OSError) as exc:
        return _check("database", "本地数据库", "error", "数据库暂时无法读取", error=type(exc).__name__)


def _secret_counts(settings: dict, manager: Any) -> tuple[int, int, int]:
    from core.security import resolve_config_secret

    protected = plaintext = missing = 0
    configs = []
    models = settings.get("models", {})
    if isinstance(models, dict):
        configs.extend(value for value in models.values() if isinstance(value, dict))
    vision = settings.get("advanced", {}).get("vision_model")
    if isinstance(vision, dict):
        configs.append(vision)
    for config in configs:
        if config.get("api_key_ref"):
            if resolve_config_secret(config, manager=manager):
                protected += 1
            else:
                missing += 1
        elif config.get("api_key"):
            plaintext += 1
    return protected, plaintext, missing


def sanitize_settings(value: Any, key: str = "") -> Any:
    """Recursively redact credentials while preserving useful structure."""
    lowered = key.lower()
    if any(part in lowered for part in _SENSITIVE_PARTS) and not lowered.endswith("_ref"):
        return "[已配置]" if value else ""
    if isinstance(value, dict):
        return {str(k): sanitize_settings(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_settings(item, key) for item in value]
    return value


def run_diagnostics(
    app_components,
    *,
    data_dir: Path,
    config_dir: Path,
    settings: dict,
    secret_manager: Any,
) -> dict:
    from core.security import resolve_config_secret

    checks: list[dict] = []
    checks.append(_check(
        "platform", "运行环境", "ok",
        f"{platform.system()} {platform.release()} · Python {platform.python_version()}",
        system=platform.system(), machine=platform.machine(), python=platform.python_version(),
        portable=os.getenv("CC_PORTABLE", "").lower() in {"1", "true", "yes", "on"},
    ))
    checks.append(_directory_check("data_directory", "数据目录", data_dir))
    checks.append(_directory_check("config_directory", "配置目录", config_dir))
    checks.append(_database_check(data_dir / "companion.db"))

    registry = getattr(app_components, "registry", None)
    available = list(getattr(registry, "available_models", []) or [])
    default_model = getattr(registry, "default_model", None)
    if default_model and default_model in available:
        checks.append(_check("model", "对话模型", "ok", f"已加载 {default_model}", count=len(available)))
    elif available:
        checks.append(_check("model", "对话模型", "warn", "模型已加载，但默认模型需要重新选择", count=len(available)))
    else:
        checks.append(_check("model", "对话模型", "error", "没有可用模型，请重新完成模型设置"))

    vision = getattr(app_components, "vision_manager", None)
    vision_config = settings.get("advanced", {}).get("vision_model", {})
    fallback_ready = bool(
        isinstance(vision_config, dict)
        and vision_config.get("model_name")
        and resolve_config_secret(vision_config, manager=secret_manager)
    )
    if bool(getattr(vision, "main_is_multimodal", False)):
        checks.append(_check("vision", "图片识别", "ok", "主模型支持直接读取图片"))
    elif fallback_ready:
        checks.append(_check("vision", "图片识别", "ok", "独立图片识别模型已配置"))
    else:
        checks.append(_check("vision", "图片识别", "warn", "当前文本模型需要配置独立图片识别模型"))

    protected, plaintext, missing = _secret_counts(settings, secret_manager)
    secret_status = secret_manager.status
    if missing:
        checks.append(_check("secrets", "密钥保护", "error", "有密钥引用无法读取，请重新填写对应密钥",
                             backend=secret_status.backend, protected=protected, missing=missing))
    elif secret_status.available and plaintext == 0:
        checks.append(_check("secrets", "密钥保护", "ok", f"系统安全存储已启用（{secret_status.backend}）",
                             backend=secret_status.backend, protected=protected))
    elif secret_status.available:
        checks.append(_check("secrets", "密钥保护", "warn", "部分旧密钥仍使用兼容存储，将在下次保存时迁移",
                             backend=secret_status.backend, protected=protected, plaintext=plaintext))
    else:
        checks.append(_check("secrets", "密钥保护", "warn", "系统安全存储不可用，已保持旧配置兼容",
                             backend=secret_status.backend, plaintext=plaintext))

    mcp = getattr(app_components, "mcp_manager", None)
    connected = int(getattr(mcp, "connected_count", 0) or 0)
    checks.append(_check(
        "mcp", "扩展工具", "ok" if connected else "warn",
        f"已连接 {connected} 个 MCP 服务" if connected else "当前没有已连接的 MCP 服务",
        connected=connected,
    ))

    counts = {status: sum(item["status"] == status for item in checks) for status in ("ok", "warn", "error")}
    overall = "error" if counts["error"] else "warn" if counts["warn"] else "ok"
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "overall": overall,
        "summary": counts,
        "checks": checks,
    }
