"""Web UI 后端 — aiohttp 网页服务

在同进程内复用已初始化的 AppComponents（pipeline / vision / registry），
提供：
- GET  /                 静态页面
- GET  /api/schema       设置字段定义（前端动态渲染）
- GET  /api/settings     当前设置有效值
- POST /api/settings     写入设置并热更新到运行中的实例
- POST /api/chat         流式对话（SSE）
- POST /api/upload/image 图片上传 + 识别
- POST /api/upload/voice 语音上传（可选 ASR，未配置则优雅降级）
- GET  /api/memory             记忆列表（分页 + 重要度过滤）
- GET  /api/memory/{id}        单条记忆详情
- GET  /api/life_summary       人生摘要列表
- GET  /api/life_summary/latest 最新一条人生摘要
- POST /api/model/provider     新增模型提供商
- DELETE /api/model/{key}      删除模型提供商

不修改核心业务逻辑，仅作为一层适配。
"""

from __future__ import annotations

import asyncio
import io
import inspect
import json
import os
import re
import tempfile
import threading
import uuid
import zipfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from loguru import logger

from core.config import (
    ROOT,
    CONFIG_DIR,
    DATA_DIR,
    DEFAULT_PERSONA_ID,
    build_web_uid,
    build_wechat_uid,
    build_memory_scope_uid,
    build_cli_uid,
    build_api_uid,
    load_advanced,
    normalize_wechat_accounts,
)
from core.persona.models import Persona
from core.runtime import run_diagnostics, sanitize_settings
from core.multimodal.stickers import StickerService
from core.llm.catalog import get_provider_spec, public_provider_catalog
from core.llm.diagnostics import discover_models, test_provider_connection
from core.llm.base import set_llm_request_id, reset_llm_request_id
from core.chat.scope_registry import ScopeExecutionRegistry
from core.security import (
    get_secret_manager,
    migrate_settings_secrets,
    model_secret_ref,
    protect_config_secret,
    resolve_config_secret,
    vision_secret_ref,
)
from core.storage.backup import (
    BACKUP_FORMAT_VERSION,
    BackupValidationError,
    create_backup,
    inspect_backup,
    pending_restore_status,
    schedule_restore,
)
from .schema import SETTINGS_SCHEMA, coerce_value
from .moments_poster import MomentsAutoPoster, load_poster_config
from .tts import TTSManager, TTSProvider, TTSStore, parse_voice_markers

STATIC_DIR = Path(__file__).resolve().parent / "static"
UPLOAD_DIR = ROOT / "data" / "uploads"
AVATAR_DIR = ROOT / "data" / "avatars"
SETTINGS_PATH = CONFIG_DIR / "settings.json"
WECHAT_CREDS_DIR = ROOT / "data" / "credentials"
MAX_IMAGE_UPLOAD_SIZE = 10 * 1024 * 1024
MAX_AUDIO_UPLOAD_SIZE = 16 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
ALLOWED_AUDIO_TYPES = {"audio/webm", "audio/ogg", "audio/wav", "audio/mpeg", "audio/mp4"}

PERSONA_ONBOARDING_DEFAULTS = {
    "system_prompt": "你是一个真实、自然、有自己生活的聊天伙伴。用纯文字和对方聊天，保持角色一致，先回应对方最在意的内容，再自然延伸话题。",
    "output_examples": "对方说：今天有点累\n你说：辛苦啦，先歇一会儿。要不要跟我说说今天发生了什么？\n\n对方说：我刚看到一只猫\n你说：在哪里看到的？可爱吗，突然有点想看你拍的照片了。",
    "persona_prompt": "你叫小可爱，温柔、活泼，偶尔有一点傲娇。你喜欢动漫、游戏和计算机，会主动分享日常，也会认真记住对方在意的事情。你们是关系亲近的朋友，聊天自然、简短，不像客服。",
}

# DEPRECATED (T9): 所有 user_id 解析应走 _resolve_user_id_from_conversation。
# 此常量仅作为 helper 内部 "无 conversation_id 且无 persona_id" 时的兜底。
WEB_USER_ID = "web_user"

# WeChat account_id validation (matches adapters/wechat.py _ACCOUNT_ID_PATTERN).
# "default" is exempt from the length requirement (backward compat).
_WECHAT_ACCOUNT_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{3,32}$")

# Per-account SSE login locks — keyed by account_id. Concurrent login to the
# same account returns 409. Module-level so locks survive across requests.
_wechat_login_locks: dict[str, asyncio.Lock] = {}

# S6.2: per-scope execution serialization + request idempotency. Module-level
# so it survives across requests; AppComponents may override with its own.
_default_scope_registry = ScopeExecutionRegistry()


# ---- 发现（朋友圈 moments）数据存储 ----
# 纯本地 JSON 存储，遵循 DATA_DIR 约定；不依赖任何模型服务。
_MOMENTS_PATH = DATA_DIR / "moments.json"
_MAX_POST_TEXT = 2000
_MAX_REPLY_TEXT = 500
_MOMENT_ID_RE = re.compile(r"^mom_[0-9a-f]{12}$")
_REPLY_ID_RE = re.compile(r"^rep_[0-9a-f]{12}$")


def _new_moment_id() -> str:
    return f"mom_{uuid.uuid4().hex[:12]}"


def _new_reply_id() -> str:
    return f"rep_{uuid.uuid4().hex[:12]}"


def _moment_now_iso() -> str:
    """朋友圈动态时间戳（本机时区 ISO）。"""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _load_moments() -> list[dict]:
    if not _MOMENTS_PATH.exists():
        return []
    try:
        return json.loads(_MOMENTS_PATH.read_text(encoding="utf-8")).get("moments") or []
    except Exception as exc:
        logger.warning(f"moments load failed: {exc}")
        return []


def _save_moments(moments: list[dict]) -> None:
    _MOMENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _MOMENTS_PATH.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps({"moments": moments}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(_MOMENTS_PATH)


def _moment_author_label(app_components, author: str) -> str:
    if author == "user":
        return "我"
    if not author:
        return ""
    try:
        loader = getattr(app_components, "persona_loader", None)
        if loader is not None:
            for p in loader.list_all():
                if p.id == author:
                    return p.name or author
    except Exception:
        pass
    return author


# ---- MCP 扩展（servers 配置）----
# 配置在 CONFIG_DIR/mcp_servers.json；MCPManager 已由 core.tools 提供连接/工具。
_MCP_SERVERS_PATH = CONFIG_DIR / "mcp_servers.json"
_MCP_ALLOWED_SERVER_FIELDS = (
    "name", "command", "args", "env", "cwd", "enabled",
    "auto_reconnect", "max_reconnect_attempts", "reconnect_base_delay",
    "reconnect_max_delay", "reconnect_backoff", "startup_timeout", "operation_timeout",
)


def _load_mcp_servers() -> list[dict]:
    if not _MCP_SERVERS_PATH.exists():
        return []
    try:
        return json.loads(_MCP_SERVERS_PATH.read_text(encoding="utf-8")).get("servers") or []
    except Exception as exc:
        logger.warning(f"MCP servers load failed: {exc}")
        return []


def _save_mcp_servers(servers: list[dict]) -> None:
    _MCP_SERVERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _MCP_SERVERS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"servers": servers}, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_MCP_SERVERS_PATH)


def _sanitize_mcp_server(raw: dict) -> dict:
    """只保留 MCP 允许的字段，杜绝未知字段写回。"""
    out = {}
    for key in _MCP_ALLOWED_SERVER_FIELDS:
        if key in raw:
            out[key] = raw[key]
    return out


def _scope_registry(app_components) -> ScopeExecutionRegistry:
    """Resolve the scope registry beside app components (testable override)."""
    custom = getattr(app_components, "scope_registry", None)
    return custom if custom is not None else _default_scope_registry


# ────────── 会话 → user_id 解析 (T9) ──────────

class _ConversationNotFound(Exception):
    """conversation_id 提供但 store 中找不到对应 binding。
    调用方应返回 404。"""


def _user_id_from_binding(binding) -> str:
    """从 ConversationBinding 推导 user_id（按 platform 分发）。"""
    platform = binding.platform
    if platform == "wechat":
        return build_wechat_uid(binding.account_id, binding.contact_id)
    if platform == "web":
        return build_web_uid(binding.persona_id)
    if platform == "cli":
        return build_cli_uid()
    if platform == "api":
        return build_api_uid(binding.contact_id)
    # 未知 platform：兜底走 web uid，避免崩溃
    logger.warning(f"WebUI: unknown platform {platform!r}, falling back to web uid")
    return build_web_uid(binding.persona_id)


def _resolve_user_id_from_conversation(
    conversation_id: str | None,
    app_components,
    fallback_persona_id: str | None = None,
) -> tuple[str, str | None, str | None]:
    """把 conversation_id 解析为 user_id。

    - conversation_id 为空/None → 走 legacy fallback：
        * 有 fallback_persona_id → build_web_uid(persona_id)
        * 无 → WEB_USER_ID（最坏情况兜底）
    - conversation_id 非空 → conversation_store.get(id) →
        * 找不到 → raise _ConversationNotFound
        * 找到 → 按 binding platform 推导 user_id

    返回 (user_id, conversation_id_or_None, persona_id_or_None)。
    - conversation_id_or_None：None 表示走 legacy 路径
    - persona_id_or_None：binding 的 persona_id（仅 conversation_id 命中时非 None）；
      POST /api/chat 应优先用这个 persona_id 喂给 pipeline
    """
    if not conversation_id:
        if fallback_persona_id:
            return build_web_uid(fallback_persona_id), None, None
        return WEB_USER_ID, None, None

    store = getattr(app_components, "conversation_store", None)
    if store is None:
        raise _ConversationNotFound("conversation_store unavailable")
    binding = store.get(conversation_id)
    if binding is None:
        raise _ConversationNotFound(conversation_id)

    # T13 legacy redirect: web:default binding 是从 legacy web_user.json 迁移来的。
    # user_id 必须用 "web_user"（走 T5 legacy 路径加载 web_user.json），而非
    # build_web_uid(persona_id)（那会指向 data/chat_history/web/{persona_id}.json，
    # legacy 历史不在那里）。此分支仅匹配 T13 migrate_legacy_web_user 创建的 binding。
    if (binding.platform == "web"
            and binding.account_id == ""
            and binding.contact_id == "default"):
        return WEB_USER_ID, conversation_id, binding.persona_id

    return _user_id_from_binding(binding), conversation_id, binding.persona_id


def _memory_scope_from_conversation(
    conversation_id: str | None,
    app_components,
    user_id: str,
    persona_id: str | None,
) -> str | None:
    """Return the isolated state namespace for a real binding.

    The migrated ``web:default`` binding deliberately keeps using the legacy
    ``web_user.json`` namespace. New bindings use a stable conversation/persona
    scope, so rebinding a contact cannot expose the previous role's memory.
    """
    if not conversation_id or not persona_id:
        return None
    store = getattr(app_components, "conversation_store", None)
    binding = store.get(conversation_id) if store is not None else None
    if (
        binding is None
        or (
            binding.platform == "web"
            and binding.account_id == ""
            and binding.contact_id == "default"
        )
    ):
        return None
    return build_memory_scope_uid(user_id, persona_id, conversation_id)


def _resolve_scoped_user_id(
    conversation_id: str | None,
    app_components,
    fallback_persona_id: str | None = None,
) -> tuple[str, str | None, str | None]:
    """Resolve a binding and return the user-facing storage scope."""
    user_id, resolved_conversation, persona_id = _resolve_user_id_from_conversation(
        conversation_id, app_components, fallback_persona_id=fallback_persona_id,
    )
    scoped = _memory_scope_from_conversation(
        resolved_conversation, app_components, user_id, persona_id,
    )
    return scoped or user_id, resolved_conversation, persona_id


def _scope_kwargs(pipeline, scope_id: str | None) -> dict:
    """Pass scope_id only to pipeline implementations that support it."""
    if not scope_id:
        return {}
    try:
        parameters = inspect.signature(pipeline.process).parameters
    except (TypeError, ValueError):
        return {}
    return {"scope_id": scope_id} if "scope_id" in parameters else {}


def _guard_client_identity(client_user_id, resolved, *, where):
    """Reject a client-supplied user_id that tries to override the resolved identity.

    Identity is authoritative (S6.1): it is derived from the conversation binding or
    the system-controlled fallback. A browser must not be able to redirect memory to
    another user by sending an arbitrary user_id. When the client supplies a user_id
    that does not match the resolved one it is a forge attempt and rejected with 403;
    an equal (or absent) value is harmless.
    """
    if isinstance(client_user_id, str):
        client_user_id = client_user_id.strip()
    if client_user_id is not None and client_user_id != "" and client_user_id != resolved:
        from aiohttp import web
        logger.warning(f"{where}: rejecting forged user_id={client_user_id!r} (resolved={resolved!r})")
        return web.json_response(
            {"error": f"{where}: user_id does not match the bound conversation identity"},
            status=403,
        )
    return None


# ────────── 设置读写 ──────────

def _load_settings() -> dict:
    """读取 settings.json，缺失返回空 dict。"""
    if SETTINGS_PATH.exists():
        try:
            return json.loads(SETTINGS_PATH.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"WebUI: failed to read settings.json: {e}")
    return {}


def _app_version() -> str:
    for distribution in ("mu-companion", "cyber-companion"):
        try:
            return version(distribution)
        except PackageNotFoundError:
            continue
    return "4.3.0"


def _save_settings(settings: dict) -> None:
    """原子写入 settings.json。"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_PATH.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    tmp.replace(SETTINGS_PATH)


def _secret_manager():
    """Resolve the secret store beside the active settings file (testable)."""
    return get_secret_manager(SETTINGS_PATH.parent)


def _migrate_existing_secrets() -> dict:
    """Move legacy plaintext keys when possible without risking availability."""
    settings = _load_settings()
    if not settings:
        status = _secret_manager().status
        return {"changed": False, "backend": status.backend, "available": status.available,
                "protected": 0, "plaintext": 0}
    migrated, report = migrate_settings_secrets(settings, manager=_secret_manager())
    if report["changed"]:
        _save_settings(migrated)
        logger.info(
            "Protected {} credential(s) with {}",
            report["protected"], report["backend"],
        )
    return report


def _current_values() -> dict:
    """按 schema 汇总当前有效值：settings.json > load_advanced 默认 > schema 默认。"""
    settings = _load_settings()
    advanced = settings.get("advanced", {})
    models = settings.get("models", {})
    default_model = settings.get("default_model")
    model_cfg = models.get(default_model, {}) if default_model else {}
    # 任取一个模型兜底（default 未设时）
    if not model_cfg and models:
        model_cfg = next(iter(models.values()))

    fallback_advanced = load_advanced()
    values: dict = {}
    for field in SETTINGS_SCHEMA:
        key = field["key"]
        target = field["target"]
        default = field["default"]
        if target == "model":
            values[key] = model_cfg.get(key, default)
        elif target == "model_repetition":
            # presence/frequency 合并展示，取 presence 为准
            values[key] = model_cfg.get("presence_penalty", default)
        else:  # advanced
            values[key] = advanced.get(key, fallback_advanced.get(key, default))
        values[key] = coerce_value(field, values[key])
    return values


def _persist_values(values: dict) -> None:
    """把 schema 值写回 settings.json 的正确位置。"""
    settings = _load_settings()
    advanced = settings.setdefault("advanced", {})
    models = settings.setdefault("models", {})
    default_model = settings.get("default_model")
    targets = [models[default_model]] if default_model and default_model in models else list(models.values())

    for field in SETTINGS_SCHEMA:
        key = field["key"]
        target = field["target"]
        val = values.get(key)
        if val is None:
            continue
        if target == "model":
            for m in targets:
                m[key] = val
        elif target == "model_repetition":
            for m in targets:
                m["presence_penalty"] = val
                m["frequency_penalty"] = val
        else:
            advanced[key] = val
    _save_settings(settings)


def _apply_live(app, values: dict) -> None:
    """热更新到运行中的实例，避免重启。"""
    # 1. 模型参数 → 直接改 LLM 实例属性
    try:
        llm = app.registry.get() if app.registry.available_models else None
    except Exception:
        llm = None
    if llm is not None:
        if "temperature" in values:
            llm.temperature = values["temperature"]
        if "max_tokens" in values:
            llm.max_tokens = values["max_tokens"]
        if "max_retries" in values:
            llm.max_retries = values["max_retries"]
        if "repetition_penalty" in values:
            llm.presence_penalty = values["repetition_penalty"]
            llm.frequency_penalty = values["repetition_penalty"]

    # 2. advanced 参数 → 更新共享 config dict
    cfg = getattr(app, "advanced_config", None)
    if isinstance(cfg, dict):
        for key in ("segment_max_length", "debounce_seconds", "summarize_threshold",
                    "proactive_enabled", "proactive_active_start", "proactive_active_end",
                    "proactive_interval_min", "proactive_interval_max", "auto_extract_memory"):
            if key in values:
                cfg[key] = values[key]

    # 3. 主动消息开关热更新
    if hasattr(app, "proactive") and app.proactive is not None:
        if "proactive_enabled" in values:
            app.proactive.enabled = values["proactive_enabled"]


# ────────── WeChat account helpers ──────────

def _validate_wechat_account_id(account_id: str) -> bool:
    """Return True if account_id is 'default' or matches ^[a-zA-Z0-9_-]{3,32}$."""
    if account_id == "default":
        return True
    return bool(_WECHAT_ACCOUNT_ID_RE.match(account_id))


def _wechat_credentials_path(account_id: str) -> Path:
    """Return the credentials file path for a wechat account_id.

    Mirrors adapters/wechat.py _credential_paths_for logic:
    - "default" → wechat.json (backward compat)
    - other     → wechat_{account_id}.json
    """
    if account_id == "default":
        return WECHAT_CREDS_DIR / "wechat.json"
    return WECHAT_CREDS_DIR / f"wechat_{account_id}.json"


def _get_wechat_accounts_config() -> list[dict]:
    """Read wechat accounts from settings.json.

    Normalizes both new array format and legacy single-object format:
    - New: advanced.adapters.wechat.accounts = [{id, persona_id, enabled, auto_start}, ...]
    - Legacy: advanced.adapters.wechat = {enabled, auto_start} (no accounts key)
    """
    settings = _load_settings()
    wechat_cfg = settings.get("advanced", {}).get("adapters", {}).get("wechat", {})
    return normalize_wechat_accounts(wechat_cfg)


def _save_wechat_accounts_config(accounts: list[dict]) -> None:
    """Write wechat accounts array to settings.json (preserves other keys)."""
    settings = _load_settings()
    settings.setdefault("advanced", {}).setdefault("adapters", {}).setdefault("wechat", {})["accounts"] = accounts
    _save_settings(settings)


def _set_runtime_wechat_accounts(app_components, accounts: list[dict]) -> None:
    """Keep live message routing aligned with account changes from the WebUI."""
    advanced = getattr(app_components, "advanced_config", None)
    if not isinstance(advanced, dict):
        return
    advanced.setdefault("adapters", {}).setdefault("wechat", {})["accounts"] = [
        dict(account) for account in accounts
    ]


def _make_session_expired_callback(account_id: str):
    """构造 session_expired 回调，注入到 WeChatAdapter.on_session_expired。

    回调由 WeChatAdapter._poll_messages 的 watchdog 在检测到 session 过期时调用
    （参数是 account_id）。回调本身只记日志 —— 前端通过 GET /api/wechat/accounts
    的 session_expired 字段轮询发现，自动弹出 QR 重登模态框。
    """
    def _on_session_expired(acc_id: str) -> None:
        logger.warning(
            f"WeChat[{acc_id}] session expired, flag set; WebUI will poll session_expired=true"
        )
    return _on_session_expired


async def _autostart_wechat_adapters(app_components) -> None:
    """服务器启动时：为 auto_start=True 且已有凭证的微信账号注册并启动 WeChatAdapter。

    遍历 settings.json 的微信账号配置，对每个 auto_start=True 且凭证文件存在的账号：
    1. 构造 WeChatAdapter(account_id=acc_id)
    2. 注册到 app_components.adapter_manager
    3. 调用 adapter.start()（复用已有凭证，不会触发二维码登录）

    无凭证的账号跳过（避免在无用户交互的服务器启动场景触发终端二维码）。
    SDK 未安装时整体跳过（避免注册一批无法启动的 adapter 占位）。
    任何单账号启动失败只 log warning，不影响其他账号或服务器启动。
    """
    adapter_manager = getattr(app_components, "adapter_manager", None)
    if adapter_manager is None:
        return

    # SDK 未安装 → 整体跳过（WeChatAdapter.start() 会静默返回，导致 registered-but-not-running 占位）
    try:
        import weixin_ilink  # type: ignore[import-not-found]  # noqa: F401
    except ImportError:
        logger.info("WeChat autostart: SDK not installed, skipping all accounts")
        return

    from adapters.wechat import WeChatAdapter

    accounts = _get_wechat_accounts_config()
    if not accounts:
        logger.info("WeChat autostart: no accounts configured in settings.json")
    for acc in accounts:
        acc_id = acc.get("id", "default")
        auto_start = acc.get("auto_start", True)
        if not auto_start:
            logger.info(f"WeChat autostart: skip {acc_id} (auto_start=false)")
            continue
        creds_path = _wechat_credentials_path(acc_id)
        if not creds_path.exists():
            logger.info(f"WeChat autostart: skip {acc_id} (no credentials)")
            continue
        # 已注册则跳过（幂等，避免重复注册）
        try:
            existing = adapter_manager.get("wechat", acc_id)
            if existing is not None:
                continue
        except Exception:
            pass
        try:
            adapter = WeChatAdapter(account_id=acc_id)
            registry = getattr(app_components, "registry", None)
            if registry is not None and getattr(registry, "available_models", None):
                try:
                    adapter._main_model = registry.get()
                except Exception:
                    pass
            # 注入 session_expired 回调（watchdog 触发后通知 WebUI）
            adapter.on_session_expired = _make_session_expired_callback(acc_id)
            adapter_manager.register(adapter, account_id=acc_id)
            await adapter.start()
            logger.info(f"WeChat autostart: started {acc_id}")
        except Exception as e:
            logger.warning(f"WeChat autostart: failed for {acc_id}: {e}")
            # 启动失败则从 manager 移除，避免残留一个未运行的 adapter 占位
            try:
                adapter_manager.unregister("wechat", acc_id)
            except Exception:
                pass


# ────────── Legacy web_user.json migration (T13) ──────────

# T13: Legacy web_user.json → web:default conversation binding migration.
# 在 _make_app 中 best-effort 调用，失败不阻塞 server 启动。
_WEB_DEFAULT_PLATFORM = "web"
_WEB_DEFAULT_ACCOUNT_ID = ""
_WEB_DEFAULT_CONTACT_ID = "default"
_MIGRATION_MARKER = ".web_user_migrated"


def migrate_legacy_web_user(conversation_store, data_dir) -> None:
    """T13: 迁移 legacy web_user.json → web:default conversation binding.

    检测条件（全部满足才创建 binding）:
    1. ``{data_dir}/.web_user_migrated`` marker 文件不存在（未迁移过）
    2. ``{data_dir}/chat_history/web_user.json`` 存在（有 legacy 历史）
    3. ``ConversationStore.find("web", "", "default")`` 返回 None（未手动创建过）

    迁移成功或判定无需迁移后写入 marker 文件（``Path.touch()``），保证幂等。
    任何异常都捕获并 log warning——迁移失败不阻塞 server 启动。

    Args:
        conversation_store: ConversationStore 实例；为 None 时直接返回。
        data_dir: 数据目录路径（str | Path）。
    """
    data_dir = Path(data_dir)
    marker = data_dir / _MIGRATION_MARKER

    if marker.exists():
        return  # 已迁移，幂等返回

    if conversation_store is None:
        return  # 无 store（测试环境 FakeAppComponents 默认 None）— 不写 marker，下次再试

    legacy_file = data_dir / "chat_history" / "web_user.json"

    # 检查 binding 是否已存在（手动创建或 race condition）— self-heal marker
    try:
        existing = conversation_store.find(
            _WEB_DEFAULT_PLATFORM, _WEB_DEFAULT_ACCOUNT_ID, _WEB_DEFAULT_CONTACT_ID
        )
    except Exception as e:
        logger.warning(f"T13 migration: find() failed: {e}")
        return

    if existing is None:
        # 无 binding — 只有 legacy 文件存在才创建
        if not legacy_file.exists():
            # 无 legacy 文件 + 无 binding — 写 marker 跳过未来检查
            try:
                marker.parent.mkdir(parents=True, exist_ok=True)
                marker.touch()
            except Exception as e:
                logger.warning(f"T13 migration: failed to write marker: {e}")
            return
        # 有 legacy 文件 + 无 binding → 创建 binding
        try:
            conversation_store.create(
                platform=_WEB_DEFAULT_PLATFORM,
                account_id=_WEB_DEFAULT_ACCOUNT_ID,
                contact_id=_WEB_DEFAULT_CONTACT_ID,
                persona_id=DEFAULT_PERSONA_ID,
            )
            logger.info("Legacy web_user.json migrated to web:default conversation")
        except ValueError as e:
            # Race condition: binding 在 find() 与 create() 之间被创建 — self-heal marker
            logger.warning(f"T13 migration: binding already exists (race): {e}")
        except Exception as e:
            # 真实失败（IO / 权限等）— 不写 marker，下次启动重试
            logger.warning(f"T13 migration: create() failed: {e}")
            return

    # 写 marker（covers: 刚创建 binding / binding 已存在 self-heal / race resolved）
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
    except Exception as e:
        logger.warning(f"T13 migration: failed to write marker: {e}")


# ────────── HTTP handlers ──────────

def _make_app(app_components):
    from aiohttp import web

    try:
        _migrate_existing_secrets()
    except Exception as exc:
        # A secure-store failure must never prevent the application from using
        # its existing environment variable or legacy plaintext credential.
        logger.warning("Secret migration skipped: {}", exc)

    routes = web.RouteTableDef()
    sticker_service = getattr(app_components, "sticker_service", None)
    if sticker_service is None:
        sticker_service = StickerService(
            DATA_DIR, STATIC_DIR / "stickers" / "pawzochat-default",
        )
        app_components.sticker_service = sticker_service
    try:
        app_components.handler.pipeline._sticker_service = sticker_service
    except AttributeError:
        pass

    @routes.get("/")
    async def index(_request):
        index_file = STATIC_DIR / "index.html"
        if index_file.exists():
            return web.FileResponse(index_file)
        return web.Response(
            text="webui/static/index.html 尚未生成", status=404
        )

    @routes.get("/api/schema")
    async def get_schema(_request):
        return web.json_response({"schema": SETTINGS_SCHEMA})

    @routes.get("/api/health")
    async def get_health(_request):
        from core.runtime import runtime_metrics
        registry = getattr(app_components, "registry", None)
        mcp = getattr(app_components, "mcp_manager", None)
        return web.json_response({
            "ok": True,
            "models": len(getattr(registry, "available_models", [])),
            "mcp_servers": getattr(mcp, "connected_count", 0),
            "runtime": runtime_metrics.snapshot(),
        })

    # ---- 发现（朋友圈）routes ----

    def _serialize_moment(m: dict) -> dict:
        replies_raw = list(m.get("replies", []) or [])
        reply_authors = {r.get("id"): r.get("author", "") for r in replies_raw}
        replies = []
        for r in replies_raw:
            rt = r.get("reply_to") or None
            rt_author = reply_authors.get(rt) if rt else None
            replies.append({
                "id": r.get("id", ""),
                "author": r.get("author", ""),
                "author_label": _moment_author_label(app_components, r.get("author", "")),
                "timestamp": r.get("timestamp", ""),
                "text": r.get("text", ""),
                "reply_to": rt,
                "reply_to_label": _moment_author_label(app_components, rt_author) if rt_author else None,
            })
        likes = [
            {"author": w, "author_label": _moment_author_label(app_components, w)}
            for w in (m.get("likes", []) or [])
        ]
        return {
            "id": m.get("id", ""),
            "author": m.get("author", ""),
            "author_label": _moment_author_label(app_components, m.get("author", "")),
            "timestamp": m.get("timestamp", ""),
            "text": m.get("text", ""),
            "likes": likes,
            "replies": replies,
        }

    def _now_iso() -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    @routes.get("/api/moments")
    async def list_moments(request):
        moments = _load_moments()
        try:
            limit = max(1, min(int(request.query.get("limit", 20)), 50))
        except ValueError:
            limit = 20
        has_more = len(moments) > limit
        return web.json_response({
            "moments": [_serialize_moment(m) for m in moments[:limit]],
            "has_more": has_more,
        })

    @routes.get("/api/moments/personas")
    async def list_moment_authors(_request):
        loader = getattr(app_components, "persona_loader", None)
        personas = []
        try:
            if loader is not None:
                personas = [{"id": p.id, "name": p.name} for p in loader.list_all()]
        except Exception as exc:
            logger.warning(f"moments personas failed: {exc}")
        return web.json_response({"personas": personas})

    @routes.post("/api/moments")
    async def publish_moment(request):
        body = await request.json()
        text = (body.get("text") or "").strip()
        author = (body.get("author") or "").strip() or "user"
        if not text:
            return web.json_response({"error": "文案不能为空"}, status=400)
        if len(text) > _MAX_POST_TEXT:
            return web.json_response({"error": "文案过长"}, status=400)
        moments = _load_moments()
        moments.insert(0, {
            "id": _new_moment_id(),
            "author": author,
            "timestamp": _now_iso(),
            "text": text,
            "likes": [],
            "replies": [],
        })
        _save_moments(moments)
        return web.json_response({"ok": True, "moment": _serialize_moment(moments[0])}, status=201)

    @routes.delete("/api/moments/{moment_id}")
    async def delete_moment(request):
        mid = request.match_info["moment_id"]
        if not _MOMENT_ID_RE.match(mid):
            return web.json_response({"error": "invalid id"}, status=400)
        moments = _load_moments()
        nxt = [m for m in moments if m.get("id") != mid]
        if len(nxt) == len(moments):
            return web.json_response({"error": "not found"}, status=404)
        _save_moments(nxt)
        return web.json_response({"ok": True})

    @routes.post("/api/moments/{moment_id}/like")
    async def like_moment(request):
        mid = request.match_info["moment_id"]
        moments = _load_moments()
        m = next((x for x in moments if x.get("id") == mid), None)
        if m is None:
            return web.json_response({"error": "not found"}, status=404)
        likes = m.setdefault("likes", [])
        if "user" not in likes:
            likes.append("user")
        _save_moments(moments)
        return web.json_response({"ok": True, "added": True})

    @routes.delete("/api/moments/{moment_id}/like")
    async def unlike_moment(request):
        mid = request.match_info["moment_id"]
        moments = _load_moments()
        m = next((x for x in moments if x.get("id") == mid), None)
        if m is None:
            return web.json_response({"error": "not found"}, status=404)
        likes = m.setdefault("likes", [])
        added = "user" in likes
        m["likes"] = [w for w in likes if w != "user"]
        _save_moments(moments)
        return web.json_response({"ok": True, "removed": added})

    @routes.post("/api/moments/{moment_id}/replies")
    async def post_reply(request):
        mid = request.match_info["moment_id"]
        body = await request.json()
        text = (body.get("text") or "").strip()
        reply_to = body.get("reply_to") or None
        if not text:
            return web.json_response({"error": "评论不能为空"}, status=400)
        if len(text) > _MAX_REPLY_TEXT:
            return web.json_response({"error": "评论过长"}, status=400)
        if reply_to is not None and not _REPLY_ID_RE.match(reply_to):
            return web.json_response({"error": "invalid reply_to"}, status=400)
        moments = _load_moments()
        m = next((x for x in moments if x.get("id") == mid), None)
        if m is None:
            return web.json_response({"error": "not found"}, status=404)
        now = _now_iso()
        r = {
            "id": _new_reply_id(),
            "author": "user",
            "timestamp": now,
            "text": text,
            "reply_to": reply_to,
        }
        m.setdefault("replies", []).append(r)
        _save_moments(moments)
        return web.json_response({"ok": True, "reply": _serialize_moment(m)["replies"][-1]}, status=201)

    @routes.delete("/api/moments/{moment_id}/replies/{reply_id}")
    async def delete_reply(request):
        mid = request.match_info["moment_id"]
        rid = request.match_info["reply_id"]
        if not _MOMENT_ID_RE.match(mid) or not _REPLY_ID_RE.match(rid):
            return web.json_response({"error": "invalid id"}, status=400)
        moments = _load_moments()
        m = next((x for x in moments if x.get("id") == mid), None)
        if m is None:
            return web.json_response({"error": "not found"}, status=404)
        before = len(m.get("replies", []))
        m["replies"] = [r for r in m.get("replies", []) if r.get("id") != rid]
        if len(m["replies"]) == before:
            return web.json_response({"error": "reply not found"}, status=404)
        _save_moments(moments)
        return web.json_response({"ok": True})

    # ---- 朋友圈自动发布（AI 自动发朋友圈）----

    def _poster_config() -> dict:
        return load_poster_config(_load_settings())

    @routes.get("/api/moments/auto/config")
    async def get_auto_config(_request):
        cfg = _poster_config()
        loader = getattr(app_components, "persona_loader", None)
        personas = []
        try:
            if loader is not None:
                personas = [{"id": p.id, "name": p.name} for p in loader.list_all()]
        except Exception as exc:
            logger.warning(f"moments auto personas failed: {exc}")
        return web.json_response({"config": cfg, "personas": personas})

    @routes.put("/api/moments/auto/config")
    async def put_auto_config(request):
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "请求格式不正确"}, status=400)
        cfg = _poster_config()
        for key in ("enabled", "interval_minutes", "persona_id", "active_start", "active_end"):
            if key in body:
                cfg[key] = body[key]
        normalized = load_poster_config({"advanced": {"moments_auto_poster": cfg}})
        settings = _load_settings()
        settings.setdefault("advanced", {})["moments_auto_poster"] = normalized
        _save_settings(settings)
        return web.json_response({"ok": True, "config": normalized})

    @routes.post("/api/moments/auto/publish")
    async def post_auto_publish(_request):
        """手动触发一次自动发布（无视时间窗口与间隔，但仍要求启用 + 指定人设）。"""
        poster = getattr(app_components, "moments_poster", None)
        if poster is None:
            return web.json_response({"error": "自动发布器未启动"}, status=503)
        poster._last_posted_at = None  # 重置间隔，强制本次发布
        published = await poster.publish_once(force=True)
        if not published:
            return web.json_response(
                {"ok": False, "error": "未发布：请在设置中启用并指定人设"},
                status=400,
            )
        return web.json_response({"ok": True})

    # ---- 插件管理（内置工具 + MCP 工具目录，只读）----

    @routes.get("/api/plugins")
    async def list_plugins(_request):
        from core.tools.base import ToolRegistry
        from core.tools.builtin import register_all

        registry = ToolRegistry()
        try:
            data_dir = str(DATA_DIR)
            register_all(registry, data_dir=data_dir)
        except Exception as e:
            logger.warning(f"plugins builtin register failed: {e}")

        builtin = []
        for tool in registry.list_tools():
            builtin.append({
                "source": "builtin",
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            })

        mcp_tools = []
        mcp = getattr(app_components, "mcp_manager", None)
        if mcp is not None:
            try:
                for t in mcp.get_all_tools():
                    mcp_tools.append({
                        "source": "mcp",
                        "name": getattr(t, "name", ""),
                        "description": getattr(t, "description", ""),
                        "server": getattr(t, "server_name", "")
                        or getattr(t, "server", "") or "",
                    })
            except Exception as e:
                logger.warning(f"plugins mcp tools failed: {e}")

        return web.json_response({
            "plugins": builtin + mcp_tools,
            "builtin_count": len(builtin),
            "mcp_count": len(mcp_tools),
            "mcp_status": mcp.get_status() if mcp is not None else None,
        })

    # ---- TTS 语音回复（服务商 CRUD + 合成）----

    def _providers_public() -> list[dict]:
        out = []
        for p in _tts_store().load_providers():
            d = p.to_dict()
            d["has_api_key"] = bool(d.pop("api_key", ""))
            out.append(d)
        return out

    @routes.get("/api/voice-providers")
    async def get_voice_providers(_request):
        store = _tts_store()
        active = store.active_provider()
        return web.json_response({
            "providers": _providers_public(),
            "active": active.name if active else None,
        })

    @routes.post("/api/voice-providers")
    async def post_voice_provider(request):
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "请求格式不正确"}, status=400)
        name = str(body.get("name") or "").strip()
        if not name:
            return web.json_response({"error": "服务商名称不能为空"}, status=400)
        store = _tts_store()
        providers = store.load_providers()
        if any(p.name == name for p in providers):
            return web.json_response({"error": "服务商已存在"}, status=409)
        providers.append(TTSProvider.from_dict(body))
        store.save_providers(providers)
        return web.json_response({"ok": True})

    @routes.put("/api/voice-providers/{name}")
    async def put_voice_provider(request):
        name = request.match_info["name"]
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "请求格式不正确"}, status=400)
        store = _tts_store()
        providers = store.load_providers()
        found = next((p for p in providers if p.name == name), None)
        if found is None:
            return web.json_response({"error": "not found"}, status=404)
        updated = TTSProvider.from_dict({**found.to_dict(), **body, "name": name})
        idx = providers.index(found)
        # 未传新 api_key 时保留旧 key（前端 masked，不发回明文）
        if not body.get("api_key") and found.api_key:
            updated.api_key = found.api_key
        providers[idx] = updated
        store.save_providers(providers)
        return web.json_response({"ok": True})

    @routes.delete("/api/voice-providers/{name}")
    async def delete_voice_provider(request):
        name = request.match_info["name"]
        store = _tts_store()
        providers = store.load_providers()
        nxt = [p for p in providers if p.name != name]
        if len(nxt) == len(providers):
            return web.json_response({"error": "not found"}, status=404)
        store.save_providers(nxt)
        return web.json_response({"ok": True})

    @routes.post("/api/voice-providers/{name}/test")
    async def test_voice_provider(request):
        name = request.match_info["name"]
        store = _tts_store()
        prov = next((p for p in store.load_providers() if p.name == name), None)
        if prov is None:
            return web.json_response({"error": "not found"}, status=404)
        try:
            data = await _tts_manager().synthesize("你好，我是慕。", provider=prov)
        except Exception as e:
            logger.warning(f"voice provider {name} test failed: {e}")
            return web.json_response({"ok": False, "error": str(e)}, status=400)
        return web.json_response({"ok": True, "bytes": len(data)})

    @routes.get("/api/audio/synthesize")
    async def synthesize_audio(request):
        """按给文字 + 可选音色合成一段语音（供试听 / 前端预合成用）。"""
        text = request.query.get("text", "").strip()
        if not text:
            return web.json_response({"error": "text 不能为空"}, status=400)
        if len(text) > 500:
            return web.json_response({"error": "text 过长"}, status=400)
        voice = request.query.get("voice", "").strip() or None
        try:
            data = await _tts_manager().synthesize(text, voice=voice)
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)}, status=400)
        return _serve_audio_bytes(request, data)

    # ---- TTS 语音合成缓存（供聊天回复 voice 渲染）----

    async def _synthesize_for_chat(persona_id: str, text: str) -> str | None:
        """真人设 + 语音服务商可用时合成语音，返回可访问的 /api/audio/... 相对 URL。

        失败 / 未配置服务商时返回 None（前端回退为纯文字）。"""
        try:
            data = await _tts_manager().synthesize(text)
        except Exception as e:
            logger.warning(f"chat TTS synthesis skipped: {e}")
            return None
        fname = f"{persona_id}_{uuid.uuid4().hex}.mp3"
        path = _tts_cache_dir() / fname
        path.write_bytes(data)
        return f"/api/audio/{persona_id}/{fname}"

    @routes.get("/api/audio/{persona_id}/{fname}")
    async def get_audio_file(request):
        pid = request.match_info["persona_id"]
        fname = request.match_info["fname"]
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", fname):
            return web.json_response({"error": "invalid name"}, status=400)
        path = _tts_cache_dir() / fname
        if not path.exists():
            return web.json_response({"error": "not found"}, status=404)
        return _serve_audio_bytes(request, path.read_bytes())

    # ---- MCP 扩展 ----

    async def _mcp_status_overlay() -> dict:
        """best-effort：从 mcp_manager 拿实时连接状态；失败返回空。"""
        mcp = getattr(app_components, "mcp_manager", None)
        if mcp is None:
            return {}
        try:
            return mcp.get_status()
        except Exception:
            return {}

    @routes.get("/api/mcp/servers")
    async def list_mcp_servers(_request):
        servers = _load_mcp_servers()
        status = await _mcp_status_overlay()
        for s in servers:
            name = s.get("name", "")
            st = status.get(name) or {}
            s["_state"] = st.get("state", "disconnected")
            s["_connected"] = bool(st.get("connected", False))
            s["_tools"] = int(st.get("tools", 0) or 0)
        return web.json_response({"servers": servers})

    @routes.post("/api/mcp/servers")
    async def add_mcp_server(request):
        body = await request.json()
        name = str(body.get("name") or "").strip()
        command = str(body.get("command") or "").strip()
        if not name:
            return web.json_response({"error": "服务名不能为空"}, status=400)
        if not command:
            return web.json_response({"error": "启动命令不能为空"}, status=400)
        servers = _load_mcp_servers()
        if any(s.get("name") == name for s in servers):
            return web.json_response({"error": f"已存在同名服务: {name}"}, status=409)
        entry = _sanitize_mcp_server(body)
        entry["name"] = name
        entry["command"] = command
        servers.append(entry)
        _save_mcp_servers(servers)
        return web.json_response({"ok": True, "server": entry}, status=201)

    @routes.put("/api/mcp/servers/{name}")
    async def update_mcp_server(request):
        name = request.match_info["name"]
        body = await request.json()
        servers = _load_mcp_servers()
        idx = next((i for i, s in enumerate(servers) if s.get("name") == name), None)
        if idx is None:
            return web.json_response({"error": "server not found"}, status=404)
        entry = _sanitize_mcp_server(body)
        entry["name"] = name
        servers[idx] = entry
        _save_mcp_servers(servers)
        return web.json_response({"ok": True, "server": entry})

    @routes.delete("/api/mcp/servers/{name}")
    async def delete_mcp_server(request):
        name = request.match_info["name"]
        servers = _load_mcp_servers()
        nxt = [s for s in servers if s.get("name") != name]
        if len(nxt) == len(servers):
            return web.json_response({"error": "server not found"}, status=404)
        _save_mcp_servers(nxt)
        return web.json_response({"ok": True})

    @routes.post("/api/mcp/connect")
    async def connect_mcp_servers(_request):
        mcp = getattr(app_components, "mcp_manager", None)
        if mcp is None:
            return web.json_response({"error": "MCP manager 不可用"}, status=503)
        try:
            connected = await mcp.load_and_connect(CONFIG_DIR)
        except Exception as exc:
            logger.warning(f"MCP connect failed: {exc}")
            return web.json_response({"error": str(exc)}, status=500)
        return web.json_response({"ok": True, "connected": connected})

    # ---- MCP per-server 控制 ----

    def _mcp_mgr_or_503():
        mcp = getattr(app_components, "mcp_manager", None)
        if mcp is None:
            return None, web.json_response({"error": "MCP manager 不可用"}, status=503)
        return mcp, None

    def _find_mcp_server(name: str):
        for s in _load_mcp_servers():
            if s.get("name") == name:
                return s
        return None

    @routes.post("/api/mcp/servers/{name}/test")
    async def test_mcp_server(request):
        name = request.match_info["name"]
        srv = _find_mcp_server(name)
        if srv is None:
            return web.json_response({"error": "server not found"}, status=404)
        mcp, err = _mcp_mgr_or_503()
        if err:
            return err
        try:
            result = await mcp.test_server(srv)
        except Exception as exc:
            logger.warning(f"MCP test {name} failed: {exc}")
            return web.json_response({"ok": False, "error": str(exc)})
        return web.json_response(result)

    @routes.post("/api/mcp/servers/{name}/connect")
    async def connect_mcp_server(request):
        name = request.match_info["name"]
        srv = _find_mcp_server(name)
        if srv is None:
            return web.json_response({"error": "server not found"}, status=404)
        mcp, err = _mcp_mgr_or_503()
        if err:
            return err
        try:
            ok = await mcp.connect_server(srv)
        except Exception as exc:
            logger.warning(f"MCP connect {name} failed: {exc}")
            return web.json_response({"error": str(exc)}, status=500)
        return web.json_response({"ok": True, "connected": ok})

    @routes.post("/api/mcp/servers/{name}/disconnect")
    async def disconnect_mcp_server(request):
        name = request.match_info["name"]
        srv = _find_mcp_server(name)
        if srv is None:
            return web.json_response({"error": "server not found"}, status=404)
        mcp, err = _mcp_mgr_or_503()
        if err:
            return err
        try:
            await mcp.disconnect_server(srv)
        except Exception as exc:
            logger.warning(f"MCP disconnect {name} failed: {exc}")
        return web.json_response({"ok": True})

    @routes.post("/api/mcp/servers/{name}/refresh")
    async def refresh_mcp_server(request):
        name = request.match_info["name"]
        srv = _find_mcp_server(name)
        if srv is None:
            return web.json_response({"error": "server not found"}, status=404)
        mcp, err = _mcp_mgr_or_503()
        if err:
            return err
        try:
            count = await mcp.refresh_server(srv)
        except Exception as exc:
            logger.warning(f"MCP refresh {name} failed: {exc}")
            return web.json_response({"error": str(exc)}, status=500)
        return web.json_response({"ok": True, "tools": count})

    @routes.get("/api/mcp/servers/{name}/tools")
    async def mcp_server_tools(request):
        name = request.match_info["name"]
        mcp, err = _mcp_mgr_or_503()
        if err:
            return err
        tools = mcp.get_server_tools(name)
        return web.json_response({
            "tools": [{"name": t.name, "description": t.description} for t in tools],
        })

    def _diagnostic_report() -> dict:
        return run_diagnostics(
            app_components,
            data_dir=DATA_DIR,
            config_dir=SETTINGS_PATH.parent,
            settings=_load_settings(),
            secret_manager=_secret_manager(),
        )

    @routes.get("/api/diagnostics")
    async def get_diagnostics(_request):
        """Run local checks without contacting model providers or exposing data."""
        return web.json_response(_diagnostic_report())

    @routes.get("/api/diagnostics/export")
    async def export_diagnostics(_request):
        """Export a sanitized support bundle without logs, messages or secrets."""
        report = _diagnostic_report()
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "diagnostics.json",
                json.dumps(report, ensure_ascii=False, indent=2),
            )
            archive.writestr(
                "settings.sanitized.json",
                json.dumps(sanitize_settings(_load_settings()), ensure_ascii=False, indent=2),
            )
        return web.Response(
            body=output.getvalue(),
            content_type="application/zip",
            headers={
                "Content-Disposition": 'attachment; filename="mu-diagnostics.zip"',
                "Cache-Control": "no-store",
            },
        )

    @routes.get("/api/stickers")
    async def list_stickers(_request):
        return web.json_response({"stickers": sticker_service.list_stickers()})

    @routes.get("/api/stickers/file/{pack}/{emotion}/{filename}")
    async def sticker_file(request):
        try:
            path = sticker_service.resolve(
                request.match_info["pack"], request.match_info["emotion"],
                request.match_info["filename"],
            )
        except (ValueError, FileNotFoundError):
            raise web.HTTPNotFound()
        return web.FileResponse(path)

    @routes.post("/api/stickers/import")
    async def import_stickers(request):
        reader = await request.multipart()
        upload = None
        pack = ""
        temp_path = DATA_DIR / f"tmp-sticker-import-{uuid.uuid4().hex}.zip"
        try:
            async for part in reader:
                if part.name == "pack":
                    pack = (await part.text()).strip()
                elif part.name in {"file", "stickers"}:
                    temp_path.parent.mkdir(parents=True, exist_ok=True)
                    with temp_path.open("wb") as output:
                        while chunk := await part.read_chunk():
                            output.write(chunk)
                    upload = temp_path
            if not upload or not pack:
                return web.json_response({"error": "pack and file are required"}, status=400)
            return web.json_response({"ok": True, **sticker_service.import_zip(upload, pack)})
        except (ValueError, zipfile.BadZipFile) as exc:
            return web.json_response({"error": str(exc)}, status=400)
        finally:
            temp_path.unlink(missing_ok=True)

    @routes.get("/api/bootstrap/status")
    async def get_bootstrap_status(_request):
        """Return the minimum state needed by the first-run Web onboarding."""
        registry = getattr(app_components, "registry", None)
        available = list(getattr(registry, "available_models", []))
        default_model = getattr(registry, "default_model", None)
        settings = _load_settings()
        persona = getattr(getattr(app_components, "persona_loader", None), "get", lambda _id: None)(DEFAULT_PERSONA_ID)
        persona_defaults = dict(PERSONA_ONBOARDING_DEFAULTS)
        for key in persona_defaults:
            value = getattr(persona, key, "") if persona is not None else ""
            if isinstance(value, str) and value.strip():
                persona_defaults[key] = value
        return web.json_response({
            "needs_setup": not bool(available and default_model),
            "needs_persona_setup": not bool(settings.get("advanced", {}).get("persona_onboarding_completed")),
            "models": available,
            "default_model": default_model,
            "persona_defaults": persona_defaults,
            "portable": bool(os.getenv("CC_PORTABLE")),
        })

    @routes.get("/api/bootstrap/providers")
    async def get_bootstrap_providers(_request):
        return web.json_response({"providers": public_provider_catalog()})

    @routes.post("/api/bootstrap/test")
    async def post_bootstrap_test(request):
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"ok": False, "code": "invalid_json", "message": "请求格式不正确"}, status=400)
        provider = str(body.get("provider") or "").strip()
        spec = get_provider_spec(provider)
        if spec is None:
            return web.json_response({"ok": False, "code": "provider", "message": "暂不支持这个服务商"}, status=400)
        result = await test_provider_connection(
            base_url=str(body.get("base_url") or spec.base_url),
            api_key=str(body.get("api_key") or ""),
            model_name=str(body.get("model_name") or spec.default_model),
        )
        return web.json_response(result, status=200 if result.get("ok") else 400)

    @routes.post("/api/bootstrap/models")
    async def post_bootstrap_models(request):
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"ok": False, "code": "invalid_json", "message": "请求格式不正确"}, status=400)
        result = await discover_models(
            base_url=str(body.get("base_url") or ""),
            api_key=str(body.get("api_key") or ""),
        )
        return web.json_response(result, status=200 if result.get("ok") else 400)

    @routes.post("/api/bootstrap/complete")
    async def post_bootstrap_complete(request):
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "请求格式不正确"}, status=400)
        provider = str(body.get("provider") or "").strip()
        spec = get_provider_spec(provider)
        if spec is None:
            return web.json_response({"error": "暂不支持这个服务商"}, status=400)
        api_key = str(body.get("api_key") or "").strip()
        model_name = str(body.get("model_name") or spec.default_model).strip()
        base_url = str(body.get("base_url") or spec.base_url).strip().rstrip("/")
        if not api_key or not model_name or len(api_key) > 512 or len(model_name) > 200:
            return web.json_response({"error": "请填写有效的 API 密钥和模型名称"}, status=400)
        settings = _load_settings()
        model_config = {
            "provider": spec.provider,
            "model_name": model_name,
            "base_url": base_url,
            "api_key": api_key,
            "max_tokens": 4096,
            "temperature": 1.0,
            "presence_penalty": 0.3,
            "frequency_penalty": 0.3,
        }
        model_config, _protected = protect_config_secret(
            model_config, model_secret_ref(provider), manager=_secret_manager()
        )
        settings.setdefault("models", {})[provider] = model_config
        settings["default_model"] = provider
        settings.setdefault("advanced", {})
        _save_settings(settings)

        registry = getattr(app_components, "registry", None)
        if registry is not None and hasattr(registry, "load_config"):
            try:
                registry.load_config(SETTINGS_PATH)
                handler = getattr(app_components, "handler", None)
                if handler is not None and hasattr(handler, "activate_default_model"):
                    handler.activate_default_model()
                vision = getattr(app_components, "vision_manager", None)
                if vision is not None and hasattr(vision, "update_main_model"):
                    vision.update_main_model(registry.get())
            except Exception as e:
                logger.warning(f"WebUI bootstrap registry reload failed: {e}")
                return web.json_response({"ok": True, "restart_required": True, "model": provider})
        return web.json_response({"ok": True, "restart_required": False, "model": provider})

    @routes.post("/api/bootstrap/persona")
    async def post_bootstrap_persona(request):
        """Save the three beginner-friendly persona fields and finish onboarding."""
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "请求格式不正确"}, status=400)
        fields = {}
        for key in ("system_prompt", "output_examples", "persona_prompt"):
            value = body.get(key, "")
            if value is None:
                value = ""
            if not isinstance(value, str):
                return web.json_response({"error": f"{key} 必须是文本"}, status=400)
            value = value.strip()
            if len(value) > 20000:
                return web.json_response({"error": "人设文本过长，请控制在 20000 字以内"}, status=400)
            fields[key] = value
        loader = getattr(app_components, "persona_loader", None)
        persona = loader.get(DEFAULT_PERSONA_ID) if loader is not None else None
        if persona is None:
            return web.json_response({"error": "默认人设不存在，请先创建一个人设"}, status=409)
        updated = loader.update(DEFAULT_PERSONA_ID, **fields)
        if updated is None:
            return web.json_response({"error": "保存人设失败"}, status=500)
        settings = _load_settings()
        settings.setdefault("advanced", {})["persona_onboarding_completed"] = True
        _save_settings(settings)
        return web.json_response({"ok": True, "persona": {"id": updated.id, "name": updated.name}})

    @routes.get("/api/settings")
    async def get_settings(_request):
        return web.json_response({"values": _current_values()})

    @routes.get("/api/about")
    async def get_about(_request):
        return web.json_response({
            "name": "慕",
            "version": _app_version(),
            "license": "MIT",
            "storage": str(DATA_DIR.resolve()),
            "backup_format_version": BACKUP_FORMAT_VERSION,
            "privacy": "对话与人设默认只保存在本机。模型服务仅在发送消息时接收必要的对话内容。",
            "tagline": "慕，只是你夜航时偶遇的浮灯，它能温柔你回望的旧岸，却无法替你横渡真实的黎明。",
        })

    @routes.post("/api/backup")
    async def post_backup(_request):
        try:
            archive = create_backup(DATA_DIR, CONFIG_DIR)
            return web.FileResponse(
                archive,
                headers={
                    "Content-Disposition": f'attachment; filename="{archive.name}"',
                    "Cache-Control": "no-store",
                },
            )
        except Exception as e:
            logger.exception(f"WebUI backup failed: {e}")
            return web.json_response({"error": "backup creation failed"}, status=500)

    @routes.post("/api/backup/inspect")
    async def inspect_uploaded_backup(request):
        """Validate a selected backup before offering an offline restore."""
        try:
            reader = await request.multipart()
            part = await reader.next()
            if part is None or part.name != "backup":
                return web.json_response({"error": "backup file required"}, status=400)
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as temp:
                temp_path = Path(temp.name)
                size = 0
                while chunk := await part.read_chunk():
                    size += len(chunk)
                    if size > 512 * 1024 * 1024:
                        temp_path.unlink(missing_ok=True)
                        return web.json_response({"error": "backup too large"}, status=413)
                    temp.write(chunk)
            try:
                manifest = inspect_backup(temp_path)
                return web.json_response({"ok": True, "manifest": manifest})
            finally:
                temp_path.unlink(missing_ok=True)
        except BackupValidationError as e:
            return web.json_response({"error": str(e)}, status=400)
        except Exception as e:
            logger.error(f"WebUI backup inspection failed: {e}")
            return web.json_response({"error": "backup inspection failed"}, status=500)

    @routes.get("/api/restore/status")
    async def get_restore_status(_request):
        pending = pending_restore_status(DATA_DIR)
        return web.json_response({"pending": bool(pending), "restore": pending})

    @routes.post("/api/restore")
    async def schedule_uploaded_restore(request):
        """Validate and queue a restore; never replace open SQLite files here."""
        temp_path = None
        try:
            reader = await request.multipart()
            part = await reader.next()
            if part is None or part.name != "backup":
                return web.json_response({"error": "backup file required"}, status=400)
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as temp:
                temp_path = Path(temp.name)
                size = 0
                while chunk := await part.read_chunk():
                    size += len(chunk)
                    if size > 512 * 1024 * 1024:
                        return web.json_response({"error": "backup too large"}, status=413)
                    temp.write(chunk)
            queued = schedule_restore(temp_path, DATA_DIR)
            return web.json_response({
                "ok": True,
                "restart_required": True,
                "restore": queued,
            })
        except BackupValidationError as e:
            return web.json_response({"error": str(e)}, status=400)
        except Exception as e:
            logger.exception(f"WebUI restore scheduling failed: {e}")
            return web.json_response({"error": "restore scheduling failed"}, status=500)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    @routes.post("/api/settings")
    async def post_settings(request):
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)

        incoming = body.get("values", body) or {}
        clean: dict = {}
        for field in SETTINGS_SCHEMA:
            key = field["key"]
            if key in incoming:
                clean[key] = coerce_value(field, incoming[key])

        if not clean:
            return web.json_response({"error": "no valid fields"}, status=400)

        try:
            _persist_values(clean)
            _apply_live(app_components, clean)
        except Exception as e:
            logger.error(f"WebUI: apply settings failed: {e}")
            return web.json_response({"error": str(e)}, status=500)

        return web.json_response({"ok": True, "values": _current_values()})

    @routes.get("/api/model")
    async def get_model(_request):
        """返回当前模型 + 可用模型列表。"""
        try:
            settings = _load_settings()
            return web.json_response({
                "current": settings.get("default_model"),
                "available": list(settings.get("models", {}).keys()),
            })
        except Exception as e:
            logger.error(f"WebUI get_model error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    @routes.post("/api/model")
    async def post_model(request):
        """切换默认模型（写 settings.json，下次启动生效，不热切换）。"""
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)
        try:
            model = body.get("model")
            if not model:
                return web.json_response({"error": "model required"}, status=400)
            settings = _load_settings()
            available = list(settings.get("models", {}).keys())
            if model not in available:
                return web.json_response(
                    {"error": f"model not found: {model}", "available": available},
                    status=400,
                )
            settings["default_model"] = model
            _save_settings(settings)
            logger.info(f"WebUI model switched to {model} (effective on next restart)")
            return web.json_response({
                "ok": True,
                "message": "模型已切换，下次启动生效",
                "current": model,
            })
        except Exception as e:
            logger.error(f"WebUI post_model error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    @routes.get("/api/memory")
    async def get_memories_list(request):
        """返回用户记忆列表（分页 + 重要度过滤）。"""
        memory_mgr = getattr(app_components, "memory_mgr", None)
        if memory_mgr is None:
            return web.json_response(
                {"error": "memory subsystem unavailable"}, status=503
            )
        try:
            try:
                user_id, _conv, _pid = _resolve_scoped_user_id(
                    request.query.get("conversation_id"), app_components,
                    fallback_persona_id=request.query.get("persona_id"),
                )
            except _ConversationNotFound as e:
                return web.json_response(
                    {"error": f"conversation not found: {e}"}, status=404
                )
            offset = int(request.query.get("offset", 0))
            limit = int(request.query.get("limit", 20))
            level_min = int(request.query.get("level_min", 1))
            level_max = int(request.query.get("level_max", 5))
            offset = max(0, offset)
            limit = max(1, min(100, limit))
            level_min = max(1, min(5, level_min))
            level_max = max(1, min(5, level_max))
            if level_min > level_max:
                return web.json_response(
                    {"error": "level_min must be <= level_max"}, status=400
                )
            all_memories = memory_mgr.get_memories(
                user_id, level_min, level_max, limit=999
            )
            total = len(all_memories)
            page = all_memories[offset: offset + limit]
            items = [
                {
                    "id": m.id,
                    "content": m.content,
                    "level": m.level,
                    "category": m.category,
                    "created_at": m.created_at,
                    "tags": m.tags,
                    "source": m.source,
                    "confidence": m.confidence,
                    "last_accessed": m.last_accessed,
                }
                for m in page
            ]
            return web.json_response({"messages": items, "total": total})
        except ValueError as e:
            return web.json_response(
                {"error": f"invalid integer parameter: {e}"}, status=400
            )
        except Exception as e:
            logger.error(f"WebUI get_memories error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    @routes.get("/api/memory/{memory_id}")
    async def get_memory_detail(request):
        """返回单条记忆的完整数据。"""
        memory_mgr = getattr(app_components, "memory_mgr", None)
        if memory_mgr is None:
            return web.json_response(
                {"error": "memory subsystem unavailable"}, status=503
            )
        memory_id = request.match_info["memory_id"]
        try:
            try:
                user_id, _conv, _pid = _resolve_scoped_user_id(
                    request.query.get("conversation_id"), app_components,
                    fallback_persona_id=request.query.get("persona_id"),
                )
            except _ConversationNotFound as e:
                return web.json_response(
                    {"error": f"conversation not found: {e}"}, status=404
                )
            memory = memory_mgr.get_memory(user_id, memory_id)
            if memory is None:
                return web.json_response({"error": "memory not found"}, status=404)
            return web.json_response({
                "id": memory.id,
                "content": memory.content,
                "level": memory.level,
                "category": memory.category,
                "created_at": memory.created_at,
                "last_accessed": memory.last_accessed,
                "access_count": memory.access_count,
                "tags": memory.tags,
                "related_memory_ids": memory.related_memory_ids,
                "superseded_by": memory.superseded_by,
                "source": memory.source,
                "confidence": memory.confidence,
                "forget_score": memory.forget_score,
                "archived": memory.archived,
            })
        except Exception as e:
            logger.error(f"WebUI get_memory error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    @routes.delete("/api/memory/{memory_id}")
    async def delete_memory(request):
        """删除一条重要度记忆（SQLite + 向量存储）。
        user_id 解析与 GET /api/memory 保持一致：优先 conversation_id，
        无则回退 WEB_USER_ID。大脑日记（life_summary）不在此路由范围内。"""
        memory_mgr = getattr(app_components, "memory_mgr", None)
        if memory_mgr is None:
            return web.json_response(
                {"error": "memory subsystem unavailable"}, status=503
            )
        memory_id = request.match_info["memory_id"]
        try:
            try:
                user_id, _conv, _pid = _resolve_scoped_user_id(
                    request.query.get("conversation_id"), app_components,
                    fallback_persona_id=request.query.get("persona_id"),
                )
            except _ConversationNotFound as e:
                return web.json_response(
                    {"error": f"conversation not found: {e}"}, status=404
                )
            deleted = memory_mgr.delete_memory(user_id, memory_id)
            if not deleted:
                return web.json_response(
                    {"error": "memory not found"}, status=404
                )
            logger.info(f"WebUI deleted memory {memory_id} for user {user_id}")
            return web.json_response({"ok": True})
        except Exception as e:
            logger.error(f"WebUI delete_memory error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    @routes.get("/api/life_summary")
    async def get_life_summaries(request):
        """返回人生摘要列表。"""
        life_summary = getattr(app_components, "life_summary", None)
        if life_summary is None:
            return web.json_response(
                {"error": "memory subsystem unavailable"}, status=503
            )
        try:
            try:
                requested_persona_id = str(request.query.get("persona_id") or "").strip()
                user_id, _conv, persona_id = _resolve_scoped_user_id(
                    request.query.get("conversation_id"), app_components,
                    fallback_persona_id=requested_persona_id,
                )
            except _ConversationNotFound as e:
                return web.json_response(
                    {"error": f"conversation not found: {e}"}, status=404
                )
            limit = int(request.query.get("limit", 20))
            limit = max(1, min(100, limit))
            summaries = life_summary._sqlite_storage.load_by_user(
                user_id, limit, persona_id or requested_persona_id,
            )
            items = [
                {
                    "id": s.id,
                    "summary_type": s.summary_type,
                    "summary": s.summary,
                    "recent_status": s.recent_status,
                    "key_events": s.key_events,
                    "message_count": s.message_count,
                    "created_at": s.created_at,
                    "emotional_trends": s.emotional_trends,
                }
                for s in summaries
            ]
            counter = getattr(life_summary._sqlite_storage, "count_by_user", None)
            total = (
                counter(user_id, persona_id or requested_persona_id)
                if counter is not None else len(summaries)
            )
            return web.json_response({"summaries": items, "total": total})
        except ValueError as e:
            return web.json_response(
                {"error": f"invalid integer parameter: {e}"}, status=400
            )
        except Exception as e:
            logger.error(f"WebUI get_life_summaries error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    @routes.get("/api/life_summary/latest")
    async def get_life_summary_latest(request):
        """返回最新一条人生摘要。"""
        life_summary = getattr(app_components, "life_summary", None)
        if life_summary is None:
            return web.json_response(
                {"error": "memory subsystem unavailable"}, status=503
            )
        try:
            try:
                requested_persona_id = str(request.query.get("persona_id") or "").strip()
                user_id, _conv, persona_id = _resolve_scoped_user_id(
                    request.query.get("conversation_id"), app_components,
                    fallback_persona_id=requested_persona_id,
                )
            except _ConversationNotFound as e:
                return web.json_response(
                    {"error": f"conversation not found: {e}"}, status=404
                )
            s = life_summary._sqlite_storage.load_latest(
                user_id, persona_id or requested_persona_id,
            )
            if s is None:
                return web.json_response(None)
            return web.json_response({
                "id": s.id,
                "summary_type": s.summary_type,
                "summary": s.summary,
                "recent_status": s.recent_status,
                "key_events": s.key_events,
                "message_count": s.message_count,
                "created_at": s.created_at,
                "emotional_trends": s.emotional_trends,
            })
        except Exception as e:
            logger.error(f"WebUI get_life_summary_latest error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    @routes.post("/api/model/provider")
    async def add_model_provider(request):
        """添加一个新的模型提供商配置到 settings.json。

        统一字段名（与 core/llm/registry.py._register_from_config 对齐）：
        provider / model_name / base_url / api_key /
        temperature / max_tokens / presence_penalty / frequency_penalty
        """
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)
        try:
            key = (body.get("key") or "").strip()
            provider = (body.get("provider") or "").strip()
            model_name = (body.get("model_name") or "").strip()
            base_url = (body.get("base_url") or "").strip()
            api_key = (body.get("api_key") or "").strip()
            if not key:
                return web.json_response({"error": "key required"}, status=400)
            if not provider:
                return web.json_response({"error": "provider required"}, status=400)
            if not model_name:
                return web.json_response({"error": "model_name required"}, status=400)
            if not base_url:
                return web.json_response({"error": "base_url required"}, status=400)
            if not api_key:
                return web.json_response({"error": "api_key required"}, status=400)
            temperature = body.get("temperature", 1.0)
            try:
                temperature = float(temperature)
            except (TypeError, ValueError):
                return web.json_response(
                    {"error": "temperature must be numeric"}, status=400
                )
            max_tokens = body.get("max_tokens", 2048)
            try:
                max_tokens = int(max_tokens)
            except (TypeError, ValueError):
                return web.json_response(
                    {"error": "max_tokens must be integer"}, status=400
                )
            presence_penalty = body.get("presence_penalty", 0.3)
            frequency_penalty = body.get("frequency_penalty", 0.3)
            try:
                presence_penalty = float(presence_penalty)
                frequency_penalty = float(frequency_penalty)
            except (TypeError, ValueError):
                return web.json_response(
                    {"error": "presence_penalty/frequency_penalty must be numeric"},
                    status=400,
                )
            settings = _load_settings()
            models = settings.setdefault("models", {})
            if key in models:
                return web.json_response(
                    {"error": "model key already exists"}, status=400
                )
            model_config = {
                "provider": provider,
                "model_name": model_name,
                "base_url": base_url,
                "api_key": api_key,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "presence_penalty": presence_penalty,
                "frequency_penalty": frequency_penalty,
            }
            model_config, _protected = protect_config_secret(
                model_config, model_secret_ref(key), manager=_secret_manager()
            )
            models[key] = model_config
            _save_settings(settings)
            logger.info(
                f"WebUI model provider added: key={key} provider={provider} "
                f"model_name={model_name}"
            )
            return web.json_response({"ok": True, "key": key})
        except Exception as e:
            logger.error(f"WebUI add_model_provider error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    @routes.get("/api/vision/config")
    async def get_vision_config(_request):
        settings = _load_settings()
        config = settings.get("advanced", {}).get("vision_model", {})
        if not isinstance(config, dict):
            config = {}
        registry = getattr(app_components, "registry", None)
        main_model = ""
        if registry is not None and getattr(registry, "available_models", None):
            try:
                main_model = str(getattr(registry.get(), "model_name", "") or "")
            except Exception:
                pass
        vision = getattr(app_components, "vision_manager", None)
        return web.json_response({
            "provider": str(config.get("provider") or "openai"),
            "model_name": str(config.get("model_name") or ""),
            "base_url": str(config.get("base_url") or ""),
            "has_api_key": bool(resolve_config_secret(
                config,
                env_value=os.getenv("OPENAI_API_KEY", ""),
                manager=_secret_manager(),
            )),
            "main_model": main_model,
            "main_is_multimodal": bool(getattr(vision, "main_is_multimodal", False)),
        })

    @routes.post("/api/vision/config")
    async def post_vision_config(request):
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "请求格式不正确"}, status=400)
        values = {}
        for key in ("provider", "model_name", "base_url", "api_key"):
            value = body.get(key, "")
            if not isinstance(value, str):
                return web.json_response({"error": f"{key} 必须是文本"}, status=400)
            values[key] = value.strip()
        if any(len(value) > 512 for value in values.values()):
            return web.json_response({"error": "视觉模型配置过长"}, status=400)
        if values["base_url"] and not re.match(r"^https?://", values["base_url"], re.I):
            return web.json_response({"error": "请填写有效的视觉模型 API 地址"}, status=400)

        settings = _load_settings()
        advanced = settings.setdefault("advanced", {})
        existing = advanced.get("vision_model", {})
        if not isinstance(existing, dict):
            existing = {}
        api_key = values["api_key"] or resolve_config_secret(
            existing,
            env_value=os.getenv("OPENAI_API_KEY", ""),
            manager=_secret_manager(),
        )
        if values["model_name"] and not api_key and not os.getenv("OPENAI_API_KEY"):
            return web.json_response({"error": "请填写视觉模型 API 密钥"}, status=400)
        runtime_config = {
            "provider": values["provider"] or "openai",
            "model_name": values["model_name"],
            "base_url": values["base_url"].rstrip("/"),
            "api_key": api_key,
        }
        stored_config, _protected = protect_config_secret(
            runtime_config,
            vision_secret_ref(),
            manager=_secret_manager(),
        )
        advanced["vision_model"] = stored_config
        _save_settings(settings)
        if isinstance(getattr(app_components, "advanced_config", None), dict):
            app_components.advanced_config["vision_model"] = dict(runtime_config)
        vision = getattr(app_components, "vision_manager", None)
        if vision is not None and hasattr(vision, "update_config"):
            vision.update_config(runtime_config)
        return web.json_response({
            "ok": True,
            "provider": runtime_config["provider"],
            "model_name": runtime_config["model_name"],
            "base_url": runtime_config["base_url"],
            "has_api_key": bool(api_key),
        })

    @routes.post("/api/model/discover")
    async def discover_model_provider(request):
        """Discover models for the settings page without browser-side API calls."""
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"ok": False, "message": "请求格式不正确"}, status=400)
        result = await discover_models(
            base_url=str(body.get("base_url") or ""),
            api_key=str(body.get("api_key") or ""),
        )
        return web.json_response(result, status=200 if result.get("ok") else 400)

    @routes.delete("/api/model/{model_key}")
    async def delete_model_provider(request):
        """删除一个模型提供商配置。"""
        model_key = request.match_info["model_key"]
        try:
            settings = _load_settings()
            models = settings.get("models", {})
            if model_key not in models:
                return web.json_response(
                    {"error": "model key not found"}, status=404
                )
            if len(models) == 1:
                return web.json_response(
                    {"error": "cannot delete last model"}, status=400
                )
            removed = models[model_key]
            reference = str(removed.get("api_key_ref") or "") if isinstance(removed, dict) else ""
            del models[model_key]
            if settings.get("default_model") == model_key:
                settings["default_model"] = next(iter(models))
            _save_settings(settings)
            if reference:
                _secret_manager().delete(reference)
            logger.info(f"WebUI model provider deleted: key={model_key}")
            return web.json_response({
                "ok": True,
                "current": settings.get("default_model"),
            })
        except Exception as e:
            logger.error(f"WebUI delete_model_provider error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    @routes.get("/api/history")
    async def get_history(request):
        """返回当前用户的消息历史（脱敏，不含 emotion 内部元数据）。"""
        try:
            try:
                user_id, _conv, _pid = _resolve_scoped_user_id(
                    request.query.get("conversation_id"), app_components,
                    # legacy (no-conversation) web refresh reads the same
                    # persona scope that legacy chat writes to, not WEB_USER_ID.
                    fallback_persona_id=(
                        request.query.get("persona_id") or DEFAULT_PERSONA_ID
                    ),
                )
            except _ConversationNotFound as e:
                return web.json_response(
                    {"error": f"conversation not found: {e}"}, status=404
                )
            # S6.1: identity is authoritative — reject a query user_id mismatch.
            forged = _guard_client_identity(
                request.query.get("user_id"), user_id, where="/api/history",
            )
            if forged is not None:
                return forged
            msgs = app_components.chat_history.get_messages(user_id)
            sanitized = [
                {
                    "role": m.get("role"),
                    "content": m.get("content"),
                    "timestamp": m.get("timestamp"),
                    **({"sticker": m["sticker"]} if m.get("sticker") else {}),
                }
                for m in msgs
            ]
            return web.json_response({"messages": sanitized})
        except Exception as e:
            logger.error(f"WebUI get_history error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    @routes.delete("/api/history/last")
    async def delete_last_message_pair(request):
        """删除最后一对消息（user+assistant），用于前端"重新生成"场景。"""
        try:
            conversation_id = request.query.get("conversation_id")
            resolved_user, _conv, _pid = _resolve_user_id_from_conversation(
                conversation_id, app_components,
                # legacy (no-conversation) regen operates on the same persona
                # scope that legacy chat writes to, not WEB_USER_ID.
                fallback_persona_id=(
                    request.query.get("persona_id") or DEFAULT_PERSONA_ID
                ),
            )
            scope_id = _memory_scope_from_conversation(
                _conv, app_components, resolved_user, _pid,
            )
            user_id = scope_id or resolved_user
            # S6.1: identity is authoritative — reject a query user_id mismatch.
            forged = _guard_client_identity(
                request.query.get("user_id"), user_id, where="/api/history/last",
            )
            if forged is not None:
                return forged
            # S6.2: /regen must take the same scope lock as a normal message so
            # it can never interleave with an in-flight generation.
            registry = _scope_registry(app_components)
            async with registry.run_exclusive(scope_id):
                app_components.chat_history.delete_last_messages(user_id)
                remaining = app_components.chat_history.get_messages(user_id)
            return web.json_response({"ok": True, "remaining": len(remaining)})
        except Exception as e:
            logger.error(f"WebUI delete_last error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    @routes.post("/api/chat")
    async def chat(request):
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)

        content = (body.get("content") or "").strip()
        if not content:
            return web.json_response({"error": "content is required"}, status=400)
        body_persona_id = body.get("persona_id") or DEFAULT_PERSONA_ID
        # T9: 优先用 conversation_id 解析 user_id；缺省走 build_web_uid(persona_id)
        try:
            user_id, _conv, binding_persona_id = _resolve_user_id_from_conversation(
                body.get("conversation_id"), app_components,
                fallback_persona_id=body_persona_id,
            )
        except _ConversationNotFound as e:
            return web.json_response(
                {"error": f"conversation not found: {e}"}, status=404
            )
        # conversation_id 命中时优先用 binding 的 persona_id（保证与该会话绑定一致）；
        # 否则用 body 里的 persona_id
        persona_id = binding_persona_id or body_persona_id
        scope_id = _memory_scope_from_conversation(
            _conv, app_components, user_id, persona_id,
        )
        # S6.1: identity is authoritative. A browser-supplied user_id may not
        # override the conversation-bound identity; reject any mismatch.
        forged = _guard_client_identity(body.get("user_id"), user_id, where="/api/chat")
        if forged is not None:
            return forged
        sticker_meta = None
        raw_sticker = body.get("sticker")
        if isinstance(raw_sticker, dict):
            try:
                sticker_service.resolve(
                    str(raw_sticker.get("pack", "")),
                    str(raw_sticker.get("emotion", "")),
                    str(raw_sticker.get("filename", "")),
                )
                sticker_meta = {
                    "pack": str(raw_sticker.get("pack")),
                    "emotion": str(raw_sticker.get("emotion")),
                    "filename": str(raw_sticker.get("filename")),
                    "url": (
                        f"/api/stickers/file/{raw_sticker.get('pack')}/"
                        f"{raw_sticker.get('emotion')}/{raw_sticker.get('filename')}"
                    ),
                }
            except (ValueError, FileNotFoundError):
                return web.json_response({"error": "invalid sticker"}, status=400)

        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "text/event-stream; charset=utf-8",
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )
        await response.prepare(request)

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def on_token(token: str):
            loop.call_soon_threadsafe(queue.put_nowait, ("token", {"token": token}))

        def on_event(event: str, data: dict):
            # Event payloads are deliberately small and never contain raw tool
            # output; this keeps the activity panel useful without leaking
            # connector data into the browser.
            loop.call_soon_threadsafe(queue.put_nowait, (event, data))

        pipeline = app_components.handler.pipeline
        registry = _scope_registry(app_components)
        # S6.3: request_id enables idempotent retries: re-submitting the same
        # scope + request_id returns the recorded result without re-calling the
        # model. Honours the X-Request-ID header or a body request_id.
        request_id = str(
            body.get("request_id") or request.headers.get("X-Request-ID") or ""
        ).strip()
        dedup = bool(request_id)

        async def _generate():
            # Streaming callbacks are set up lazily so a deduplicated request
            # (which returns a recorded result) never re-streams or re-runs.
            kwargs = {"on_token": on_token}
            try:
                parameters = inspect.signature(pipeline.process).parameters
            except (TypeError, ValueError):
                parameters = {}
            if "on_event" in parameters:
                kwargs["on_event"] = on_event
            if "sticker" in parameters:
                kwargs["sticker"] = sticker_meta
            if scope_id and "scope_id" in parameters:
                kwargs["scope_id"] = scope_id
            # The pipeline already returns friendly user-facing error strings
            # internally; unexpected exceptions propagate to the SSE loop's
            # error handler below.
            # §8.4: bind the request_id so every LLM log line is traceable
            # (desensitized; never logs keys or full prompts).
            _llm_req_token = set_llm_request_id(request_id)
            try:
                return await pipeline.process(
                    user_id, content, persona_id, **kwargs,
                )
            finally:
                reset_llm_request_id(_llm_req_token)

        async def _run():
            try:
                # S6.2/S6.3: submit() takes the per-scope lock (one scope runs
                # one generation at a time; different scopes run concurrently)
                # and dedups repeated (scope, request_id) so a retry never
                # re-invokes the model. A cancellation while waiting leaves the
                # lock cleanly and a disconnected client never blocks forever.
                return await registry.submit(
                    scope_id, request_id or uuid.uuid4().hex,
                    _generate, dedup=dedup and bool(scope_id),
                )
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        task = asyncio.create_task(_run())

        async def _send(event: str, data: dict):
            payload = json.dumps(data, ensure_ascii=False)
            await response.write(
                f"event: {event}\ndata: {payload}\n\n".encode("utf-8")
            )

        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                event, data = item
                await _send(event, data)
            reply, level = await task
            # TTS 语音回复：若回复带 [语音]/[voice] 标记且配置了语音服务商，
            # 则异步合成语音并附带 voice_url；失败/未配置时仅发纯文字（标记已剥离）。
            display_reply, want_voice = parse_voice_markers(reply)
            voice_url = None
            if want_voice and display_reply:
                try:
                    voice_url = await _synthesize_for_chat(persona_id, display_reply)
                except Exception as e:
                    logger.warning(f"chat TTS hook failed: {e}")
            await _send("done", {
                "reply": display_reply,
                "level": level,
                "voice_url": voice_url,
            })
        except Exception as e:
            logger.error(f"WebUI chat error: {e}")
            try:
                await _send("error", {"error": "暂时无法生成回复，请稍后重试"})
            except Exception:
                pass
        finally:
            if not task.done():
                task.cancel()
            try:
                await response.write_eof()
            except Exception:
                pass
        return response

    @routes.post("/api/upload/image")
    async def upload_image(request):
        vision = getattr(app_components, "vision_manager", None)
        pipeline = app_components.handler.pipeline

        reader = await request.multipart()
        image_path = None
        caption = ""
        conversation_id = ""
        user_id_override = ""
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

        async for part in reader:
            if part.name == "image":
                content_type = (part.headers.get("Content-Type") or "").split(";", 1)[0].lower()
                if content_type not in ALLOWED_IMAGE_TYPES:
                    return web.json_response({"error": "unsupported image type"}, status=415)
                ext = Path(part.filename or "img.png").suffix or ".png"
                image_path = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
                size = 0
                with open(image_path, "wb") as f:
                    while True:
                        chunk = await part.read_chunk()
                        if not chunk:
                            break
                        size += len(chunk)
                        if size > MAX_IMAGE_UPLOAD_SIZE:
                            f.close()
                            image_path.unlink(missing_ok=True)
                            return web.json_response({"error": "image too large"}, status=413)
                        f.write(chunk)
            elif part.name == "caption":
                caption = (await part.text()).strip()
            elif part.name == "conversation_id":
                conversation_id = (await part.text()).strip()
            elif part.name == "user_id":
                user_id_override = (await part.text()).strip()

        if image_path is None:
            return web.json_response({"error": "no image"}, status=400)

        if vision is None:
            return web.json_response(
                {"error": "视觉识别未配置"}, status=400
            )

        try:
            resolved_user_id, _conv, bound_persona_id = _resolve_user_id_from_conversation(
                conversation_id, app_components,
            )
        except _ConversationNotFound as e:
            return web.json_response(
                {"error": f"conversation not found: {e}"}, status=404
            )
        # S6.1: identity is authoritative — a client-form user_id may not override
        # the conversation-bound identity; reject any mismatch.
        forged = _guard_client_identity(user_id_override, resolved_user_id, where="/api/upload")
        if forged is not None:
            return forged
        user_id = resolved_user_id
        persona_id = bound_persona_id or DEFAULT_PERSONA_ID
        scope_id = _memory_scope_from_conversation(
            _conv, app_components, resolved_user_id, persona_id,
        )
        history_user_id = scope_id or user_id

        try:
            vision_prompt = (
                "请客观描述这张图片的内容：画面里有什么、是什么场景、"
                "有什么值得注意的细节。只描述事实，不要加表情、语气和评价。"
            )
            if caption:
                vision_prompt += f"\n用户补充说明：{caption}\n请结合这句话理解图片并直接回复用户。"
            vision_result = await vision.process(str(image_path), vision_prompt)
            if vision.main_is_multimodal:
                reply = vision_result
                history = getattr(app_components, "chat_history", None)
                if history is not None:
                    user_content = "[用户发送了一张图片]" + (f" {caption}" if caption else "")
                    history.add_message(
                        history_user_id, "user", user_content, platform="web",
                        persona_id=persona_id,
                    )
                    history.add_message(
                        history_user_id, "assistant", reply, platform="web",
                        persona_id=persona_id,
                    )
            else:
                enhanced = vision.build_enhanced_message(vision_result, caption)
                reply, _ = await pipeline.process(
                    user_id, enhanced, persona_id,
                    **_scope_kwargs(pipeline, scope_id),
                )
            return web.json_response({"reply": reply})
        except Exception as e:
            logger.error(f"WebUI image error: {e}")
            return web.json_response({"error": str(e)}, status=500)
        finally:
            image_path.unlink(missing_ok=True)

    @routes.post("/api/upload/voice")
    async def upload_voice(request):
        """语音上传：若配置了 ASR 则转写为文本再走对话，否则优雅降级。"""
        pipeline = app_components.handler.pipeline
        reader = await request.multipart()
        audio_path = None
        conversation_id = ""
        user_id_override = ""
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

        async for part in reader:
            if part.name == "audio":
                content_type = (part.headers.get("Content-Type") or "").split(";", 1)[0].lower()
                if content_type not in ALLOWED_AUDIO_TYPES:
                    return web.json_response({"error": "unsupported audio type"}, status=415)
                ext = Path(part.filename or "voice.webm").suffix or ".webm"
                audio_path = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
                size = 0
                with open(audio_path, "wb") as f:
                    while True:
                        chunk = await part.read_chunk()
                        if not chunk:
                            break
                        size += len(chunk)
                        if size > MAX_AUDIO_UPLOAD_SIZE:
                            f.close()
                            audio_path.unlink(missing_ok=True)
                            return web.json_response({"error": "audio too large"}, status=413)
                        f.write(chunk)
            elif part.name == "conversation_id":
                conversation_id = (await part.text()).strip()
            elif part.name == "user_id":
                user_id_override = (await part.text()).strip()

        if audio_path is None:
            return web.json_response({"error": "no audio"}, status=400)

        try:
            resolved_user_id, _conv, bound_persona_id = _resolve_user_id_from_conversation(
                conversation_id, app_components,
            )
        except _ConversationNotFound as e:
            return web.json_response(
                {"error": f"conversation not found: {e}"}, status=404
            )
        # S6.1: identity is authoritative — a client-form user_id may not override
        # the conversation-bound identity; reject any mismatch.
        forged = _guard_client_identity(user_id_override, resolved_user_id, where="/api/upload")
        if forged is not None:
            return forged
        user_id = resolved_user_id
        persona_id = bound_persona_id or DEFAULT_PERSONA_ID
        scope_id = _memory_scope_from_conversation(
            _conv, app_components, resolved_user_id, persona_id,
        )

        # S8.3: faster-whisper load + transcribe are blocking — run them off
        # the event loop so chat/SSE/wechat stay responsive while ASR works.
        text = await asyncio.to_thread(_try_transcribe, audio_path)
        if not text:
            return web.json_response(
                {"error": "语音转写未配置", "need_asr": True}, status=400
            )
        try:
            reply, _ = await pipeline.process(
                user_id, text, persona_id,
                **_scope_kwargs(pipeline, scope_id),
            )
            return web.json_response({"transcript": text, "reply": reply})
        except Exception as e:
            logger.error(f"WebUI voice error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    @routes.get("/api/persona")
    async def list_personas(_request):
        """返回人设列表（只 id+name+avatar，不含完整字段）。"""
        try:
            personas = app_components.persona_loader.list_all()
            return web.json_response([
                {"id": p.id, "name": p.name, "avatar": getattr(p, "avatar", "") or ""}
                for p in personas
            ])
        except Exception as e:
            logger.error(f"WebUI list_personas error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    @routes.get("/api/persona/{persona_id}")
    async def get_persona(request):
        """返回单个人设的 USER_FIELDS（脱敏，不含 ADVANCED_FIELDS）。"""
        persona_id = request.match_info["persona_id"]
        try:
            persona = app_components.persona_loader.get(persona_id)
            if not persona:
                return web.json_response({"error": "persona not found"}, status=404)
            data = {f: getattr(persona, f, None) for f in app_components.persona_loader.USER_FIELDS}
            data["id"] = persona.id
            return web.json_response(data)
        except Exception as e:
            logger.error(f"WebUI get_persona error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    @routes.get("/api/persona/{persona_id}/advanced")
    async def get_persona_advanced(request):
        """返回单个人设的 ADVANCED_FIELDS（高级折叠区用）。"""
        persona_id = request.match_info["persona_id"]
        try:
            persona = app_components.persona_loader.get(persona_id)
            if not persona:
                return web.json_response({"error": "persona not found"}, status=404)
            data = {f: getattr(persona, f, None) for f in app_components.persona_loader.ADVANCED_FIELDS}
            return web.json_response(data)
        except Exception as e:
            logger.error(f"WebUI get_persona_advanced error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    @routes.post("/api/persona/{persona_id}")
    async def update_persona(request):
        """更新人设字段。body: {"fields": {field: value, ...}}。
        fields 的 key 必须在 USER_FIELDS ∪ ADVANCED_FIELDS 内。
        """
        persona_id = request.match_info["persona_id"]
        try:
            persona = app_components.persona_loader.get(persona_id)
            if not persona:
                return web.json_response({"error": "persona not found"}, status=404)
            body = await request.json()
            fields = body.get("fields", {})
            loader = app_components.persona_loader
            allowed = loader.USER_FIELDS | loader.ADVANCED_FIELDS
            invalid = set(fields.keys()) - allowed
            if invalid:
                return web.json_response(
                    {"error": f"invalid fields: {invalid}"}, status=400
                )
            updated = loader.update(persona_id, **fields)
            return web.json_response({"ok": True, "persona": {"id": updated.id, "name": updated.name}})
        except Exception as e:
            logger.error(f"WebUI update_persona error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    @routes.post("/api/persona")
    async def create_persona(request):
        """新建人设。body: {"id": ..., "name": ..., "description"?}.
        id 必须唯一（不与现有 persona id 冲突）。
        description 可选，写入 background 字段（自由文本，前端编辑器可见）。
        """
        try:
            body = await request.json()
            persona_id = str(body.get("id") or "").strip()
            name = str(body.get("name") or "").strip()
            if not persona_id or not name:
                return web.json_response(
                    {"error": "id and name required"}, status=400
                )
            loader = app_components.persona_loader
            if loader.get(persona_id):
                return web.json_response(
                    {"error": "persona id already exists"}, status=409
                )
            description = str(body.get("description") or "").strip()
            persona = Persona(id=persona_id, name=name)
            if description:
                persona.background = description
            loader.add(persona)
            logger.info(f"WebUI persona created: {persona_id}")
            return web.json_response(
                {"ok": True, "persona": {"id": persona.id, "name": persona.name}}
            )
        except Exception as e:
            logger.error(f"WebUI create_persona error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    @routes.delete("/api/persona/{persona_id}")
    async def delete_persona(request):
        """删除人设。不允许删除 DEFAULT_PERSONA_ID 或最后一个人设。
        T13: PersonaLoader.delete 自动清理 avatar 孤儿文件。
        """
        persona_id = request.match_info["persona_id"]
        loader = app_components.persona_loader
        if not loader.get(persona_id):
            return web.json_response({"error": "persona not found"}, status=404)
        if persona_id == DEFAULT_PERSONA_ID:
            return web.json_response(
                {"error": "不能删除默认人设"}, status=409
            )
        if len(loader.list_all()) <= 1:
            return web.json_response(
                {"error": "至少保留一个人设"}, status=409
            )
        assigned_accounts = [
            account["id"] for account in _get_wechat_accounts_config()
            if account.get("persona_id") == persona_id
        ]
        if assigned_accounts:
            return web.json_response(
                {"error": "这个角色仍被微信账号使用，请先为账号选择其他角色"},
                status=409,
            )
        store = getattr(app_components, "conversation_store", None)
        if store is not None and any(
            binding.persona_id == persona_id for binding in store.list()
        ):
            return web.json_response(
                {"error": "这个角色仍有对话记录，请先删除对应对话"},
                status=409,
            )
        deleted = loader.delete(persona_id)
        if not deleted:
            return web.json_response({"error": "delete failed"}, status=500)
        logger.info(f"WebUI persona deleted: {persona_id}")
        return web.json_response({"ok": True})

    # ────────── 人设头像 ──────────

    AVATAR_CONTENT_TYPE_EXT = {
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/webp": "webp",
    }
    AVATAR_MAX_SIZE = 2 * 1024 * 1024  # 2MB

    @routes.post("/api/persona/{persona_id}/avatar")
    async def upload_persona_avatar(request):
        """上传人设头像。multipart/form-data, field 'file', <2MB, png/jpg/webp。
        保存为 data/avatars/{persona_id}.{ext}，更新 personas.json 的 avatar 字段。
        """
        persona_id = request.match_info["persona_id"]
        loader = app_components.persona_loader
        if not loader.get(persona_id):
            return web.json_response({"error": "persona not found"}, status=404)

        reader = await request.multipart()
        file_part = None
        async for part in reader:
            if part.name == "file":
                file_part = part
                break
        if file_part is None:
            return web.json_response({"error": "no file field"}, status=400)

        content_type = file_part.headers.get("Content-Type", "")
        ext = AVATAR_CONTENT_TYPE_EXT.get(content_type)
        if ext is None:
            return web.json_response(
                {"error": f"unsupported content type: {content_type}"}, status=415
            )

        AVATAR_DIR.mkdir(parents=True, exist_ok=True)
        # 清理旧文件（扩展名变更时防止残留）
        for old in AVATAR_DIR.glob(f"{persona_id}.*"):
            old.unlink(missing_ok=True)

        avatar_path = AVATAR_DIR / f"{persona_id}.{ext}"
        size = 0
        too_large = False
        with open(avatar_path, "wb") as f:
            while True:
                chunk = await file_part.read_chunk()
                if not chunk:
                    break
                size += len(chunk)
                if size > AVATAR_MAX_SIZE:
                    too_large = True
                    break
                f.write(chunk)

        if too_large:
            avatar_path.unlink(missing_ok=True)
            return web.json_response(
                {"error": "file too large (max 2MB)"}, status=413
            )

        avatar_url = f"/avatars/{persona_id}.{ext}"
        loader.update(persona_id, avatar=avatar_url)
        logger.info(f"WebUI avatar uploaded for {persona_id}: {avatar_url}")
        return web.json_response({"ok": True, "avatar_url": avatar_url})

    @routes.delete("/api/persona/{persona_id}/avatar")
    async def delete_persona_avatar(request):
        """删除人设头像文件 + 清空 avatar 字段。
        persona 不存在 → 404；但仍执行孤儿文件清理。
        """
        persona_id = request.match_info["persona_id"]
        loader = app_components.persona_loader
        persona = loader.get(persona_id)

        # 孤儿清理：即使 persona 已删，也尝试删文件（双重保险，T13 也做）
        AVATAR_DIR.mkdir(parents=True, exist_ok=True)
        for old in AVATAR_DIR.glob(f"{persona_id}.*"):
            old.unlink(missing_ok=True)

        if not persona:
            return web.json_response({"error": "persona not found"}, status=404)

        loader.update(persona_id, avatar="")
        logger.info(f"WebUI avatar deleted for {persona_id}")
        return web.json_response({"ok": True})

    # ────────── 会话绑定 (Conversation Binding) ──────────

    @routes.get("/api/conversations")
    async def list_conversations(_request):
        """返回所有会话绑定，每条附带 persona name。"""
        try:
            store = app_components.conversation_store
            persona_loader = app_components.persona_loader
            bindings = store.list()
            result = []
            for b in bindings:
                d = b.to_dict()
                persona = persona_loader.get(b.persona_id) if persona_loader else None
                d["persona_name"] = getattr(persona, "name", "") if persona else ""
                result.append(d)
            return web.json_response(result)
        except Exception as e:
            logger.error(f"WebUI list_conversations error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    @routes.get("/api/conversations/{conversation_id}")
    async def get_conversation(request):
        """返回单个会话绑定详情。"""
        conversation_id = request.match_info["conversation_id"]
        try:
            store = app_components.conversation_store
            b = store.get(conversation_id)
            if not b:
                return web.json_response(
                    {"error": "conversation not found"}, status=404
                )
            d = b.to_dict()
            persona_loader = app_components.persona_loader
            persona = persona_loader.get(b.persona_id) if persona_loader else None
            d["persona_name"] = getattr(persona, "name", "") if persona else ""
            return web.json_response(d)
        except Exception as e:
            logger.error(f"WebUI get_conversation error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    @routes.post("/api/conversations")
    async def create_conversation(request):
        """创建会话绑定。body: {platform, account_id, contact_id, persona_id}。
        三元组重复 → 409。
        """
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)

        platform = str(body.get("platform", "")).strip()
        account_id = str(body.get("account_id", "")).strip()
        contact_id = str(body.get("contact_id", "")).strip()
        persona_id = str(body.get("persona_id", "")).strip()
        if not (platform and persona_id):
            return web.json_response(
                {"error": "platform and persona_id are required"}, status=400
            )

        # Web conversations are persona-scoped, so exposing contact_id in the
        # UI adds no value. Keep the stored triple stable without user input.
        if platform == "web" and not contact_id:
            contact_id = persona_id
        elif not contact_id:
            return web.json_response(
                {"error": "contact_id is required for WeChat conversations"},
                status=400,
            )

        try:
            store = app_components.conversation_store
            binding = store.create(platform, account_id, contact_id, persona_id)
            return web.json_response(binding.to_dict())
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=409)
        except Exception as e:
            logger.error(f"WebUI create_conversation error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    @routes.patch("/api/conversations/{conversation_id}")
    async def update_conversation(request):
        """更新会话绑定。body: {persona_id?, title?}，至少传一个。不存在 → 404。

        - persona_id：切换人设（非空串才生效）
        - title：用户自定义备注名（可传空串清除，回退显示 persona name）
        """
        conversation_id = request.match_info["conversation_id"]
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)

        persona_id = body.get("persona_id")
        title = body.get("title")

        # 至少一个可操作字段：persona_id 非空串，或 title 显式提供（含空串清除）
        if not persona_id and title is None:
            return web.json_response(
                {"error": "persona_id or title is required"}, status=400
            )

        try:
            store = app_components.conversation_store
            binding = None
            if persona_id:
                binding = store.update_persona(conversation_id, persona_id)
                if not binding:
                    return web.json_response(
                        {"error": "conversation not found"}, status=404
                    )
            if title is not None:
                binding = store.rename(conversation_id, title)
                if not binding:
                    return web.json_response(
                        {"error": "conversation not found"}, status=404
                    )
            return web.json_response(binding.to_dict())
        except Exception as e:
            logger.error(f"WebUI update_conversation error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    @routes.delete("/api/conversations/{conversation_id}")
    async def delete_conversation(request):
        """删除会话绑定。不存在 → 404。

        同时清空该对话关联的 chat_history（按 binding platform 推导 user_id，
        调 chat_history.delete_user）。chat_history 清理失败不阻塞删除，
        仅记 warning。
        """
        conversation_id = request.match_info["conversation_id"]
        try:
            store = app_components.conversation_store
            # 先拿 binding（需要 platform/account_id/contact_id/persona_id 推导 user_id）
            binding = store.get(conversation_id)
            if not binding:
                return web.json_response(
                    {"error": "conversation not found"}, status=404
                )
            ok = store.delete(conversation_id)
            if not ok:
                # 极少见：get 命中但 delete 失败（并发删除）
                return web.json_response(
                    {"error": "conversation not found"}, status=404
                )

            # 清 chat_history（按 binding 推导 user_id）
            chat_history = getattr(app_components, "chat_history", None)
            if chat_history is not None:
                try:
                    uid = _user_id_from_binding(binding)
                    scope_uid = _memory_scope_from_conversation(
                        conversation_id, app_components, uid, binding.persona_id,
                    )
                    chat_history.delete_user(scope_uid or uid)
                except Exception as e:
                    logger.warning(
                        f"WebUI: clean chat_history for conv {conversation_id} failed: {e}"
                    )
            return web.json_response({"ok": True})
        except Exception as e:
            logger.error(f"WebUI delete_conversation error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    # ────────── WeChat 账号管理 + SSE 二维码登录 (T8) ──────────

    @routes.get("/api/wechat/accounts")
    async def list_wechat_accounts(_request):
        """列出所有配置的微信账号 + 状态（has_credentials / adapter_running / session_expired）。"""
        try:
            accounts = _get_wechat_accounts_config()
            adapter_manager = getattr(app_components, "adapter_manager", None)
            result = []
            for acc in accounts:
                acc_id = acc.get("id", "default")
                creds_path = _wechat_credentials_path(acc_id)
                adapter_running = False
                session_expired = False
                if adapter_manager is not None:
                    try:
                        adapter = adapter_manager.get("wechat", acc_id)
                        if adapter is not None:
                            adapter_running = True
                            # WeChatAdapter.session_expired（watchdog 触发后置 True）
                            session_expired = getattr(adapter, "session_expired", False)
                    except Exception:
                        adapter_running = False
                result.append({
                    "id": acc_id,
                    "enabled": acc.get("enabled", True),
                    "auto_start": acc.get("auto_start", False),
                    "persona_id": acc.get("persona_id", DEFAULT_PERSONA_ID),
                    "persona_name": (
                        getattr(
                            app_components.persona_loader.get(
                                acc.get("persona_id", DEFAULT_PERSONA_ID)
                            ),
                            "name",
                            "",
                        )
                        if getattr(app_components, "persona_loader", None) is not None
                        else ""
                    ),
                    "has_credentials": creds_path.exists(),
                    "adapter_running": adapter_running,
                    "session_expired": session_expired,
                })
            return web.json_response(result)
        except Exception as e:
            logger.error(f"WebUI list_wechat_accounts error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    @routes.post("/api/wechat/accounts")
    async def create_wechat_account(request):
        """新增微信账号配置。body: {id, persona_id?, enabled?, auto_start?}。

        id 必须匹配 ^[a-zA-Z0-9_-]{3,32}$ 或为 "default"。
        重复 id → 409；非法 id → 400。
        """
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)
        try:
            acc_id = (body.get("id") or "").strip()
            if not acc_id:
                return web.json_response({"error": "id required"}, status=400)
            if not _validate_wechat_account_id(acc_id):
                return web.json_response(
                    {"error": "id must match ^[a-zA-Z0-9_-]{3,32}$ or be 'default'"},
                    status=400,
                )
            accounts = _get_wechat_accounts_config()
            if any(a.get("id") == acc_id for a in accounts):
                return web.json_response(
                    {"error": f"account already exists: {acc_id}"}, status=409,
                )
            explicit_persona_id = str(body.get("persona_id") or "").strip()
            persona_id = explicit_persona_id or DEFAULT_PERSONA_ID
            loader = getattr(app_components, "persona_loader", None)
            if explicit_persona_id and loader is not None and loader.get(persona_id) is None:
                return web.json_response({"error": "persona not found"}, status=400)
            new_acc = {
                "id": acc_id,
                "enabled": bool(body.get("enabled", True)),
                "auto_start": bool(body.get("auto_start", False)),
                "persona_id": persona_id,
            }
            accounts.append(new_acc)
            _save_wechat_accounts_config(accounts)
            _set_runtime_wechat_accounts(app_components, accounts)
            logger.info(f"WebUI wechat account created: {acc_id}")
            return web.json_response(new_acc)
        except Exception as e:
            logger.error(f"WebUI create_wechat_account error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    @routes.patch("/api/wechat/accounts/{account_id}")
    async def update_wechat_account(request):
        """Change the single role assigned to an external WeChat account."""
        account_id = request.match_info["account_id"]
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)
        persona_id = str(body.get("persona_id") or "").strip()
        if not persona_id:
            return web.json_response({"error": "persona_id required"}, status=400)
        loader = getattr(app_components, "persona_loader", None)
        persona = loader.get(persona_id) if loader is not None else None
        if loader is not None and persona is None:
            return web.json_response({"error": "persona not found"}, status=400)
        try:
            accounts = _get_wechat_accounts_config()
            account = next((item for item in accounts if item.get("id") == account_id), None)
            if account is None:
                return web.json_response(
                    {"error": f"account not found: {account_id}"}, status=404,
                )
            account["persona_id"] = persona_id
            _save_wechat_accounts_config(accounts)
            _set_runtime_wechat_accounts(app_components, accounts)
            synced = 0
            store = getattr(app_components, "conversation_store", None)
            if store is not None:
                synced = store.update_account_persona("wechat", account_id, persona_id)
            return web.json_response({
                "ok": True,
                "id": account_id,
                "persona_id": persona_id,
                "persona_name": getattr(persona, "name", "") if persona else "",
                "bindings_updated": synced,
            })
        except Exception as e:
            logger.error(f"WebUI update_wechat_account error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    @routes.delete("/api/wechat/accounts/{account_id}")
    async def delete_wechat_account(request):
        """删除微信账号配置 + 凭证文件 + 停止适配器（若运行中）。不存在 → 404。"""
        account_id = request.match_info["account_id"]
        try:
            accounts = _get_wechat_accounts_config()
            if not any(a.get("id") == account_id for a in accounts):
                return web.json_response(
                    {"error": f"account not found: {account_id}"}, status=404,
                )
            # 先停止 + 注销适配器（避免删除凭证后适配器仍尝试长轮询）
            adapter_manager = getattr(app_components, "adapter_manager", None)
            if adapter_manager is not None:
                try:
                    existing = adapter_manager.get("wechat", account_id)
                    if existing is not None:
                        await existing.stop()
                        adapter_manager.unregister("wechat", account_id)
                except Exception as e:
                    logger.warning(f"WeChat delete: failed to stop adapter for {account_id}: {e}")
            accounts = [a for a in accounts if a.get("id") != account_id]
            _save_wechat_accounts_config(accounts)
            _set_runtime_wechat_accounts(app_components, accounts)
            creds_path = _wechat_credentials_path(account_id)
            if creds_path.exists():
                creds_path.unlink()
            logger.info(f"WebUI wechat account deleted: {account_id}")
            return web.json_response({"ok": True})
        except Exception as e:
            logger.error(f"WebUI delete_wechat_account error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    @routes.get("/api/wechat/login/{account_id}/qrcode")
    async def wechat_login_qrcode(request):
        """SSE 二维码登录流。后端在 executor 中调用 weixin_ilink.login()。

        事件:
        - event: qrcode  data: {qr_url, qr_base64?}
        - event: status   data: {status, message}
        - event: done     data: {ok: true} | {ok: false, error: "..."}
        - 心跳: `: ping` 每 5s

        同账号并发登录 → 409。客户端断开 → 取消 executor future + 释放锁。
        """
        account_id = request.match_info["account_id"]
        accounts = _get_wechat_accounts_config()
        if not any(a.get("id") == account_id for a in accounts):
            return web.json_response(
                {"error": f"account not configured: {account_id}"}, status=404,
            )

        lock = _wechat_login_locks.setdefault(account_id, asyncio.Lock())
        if lock.locked():
            return web.json_response(
                {"error": "login already in progress for this account"},
                status=409,
            )

        async with lock:
            resp = web.StreamResponse(
                status=200,
                headers={
                    "Content-Type": "text/event-stream; charset=utf-8",
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )
            await resp.prepare(request)

            loop = asyncio.get_running_loop()
            events_queue: asyncio.Queue = asyncio.Queue()
            creds_path = _wechat_credentials_path(account_id)
            creds_path.parent.mkdir(parents=True, exist_ok=True)

            # SDK status → user-facing status mapping
            # (SDK typo "scaned" preserved as key)
            status_map = {
                "scaned": ("scanning", "请确认登录"),
                "confirmed": ("confirmed", "登录成功"),
                "expired": ("expired", "二维码过期"),
            }

            def _on_qrcode(url: str) -> None:
                """SDK 回调（executor 线程中执行）→ 推 qrcode 事件。"""
                payload: dict = {"qr_url": url}
                try:
                    import io
                    import base64 as _b64
                    import qrcode  # type: ignore[import-not-found]
                    qr = qrcode.QRCode(border=1)
                    qr.add_data(url)
                    qr.make()
                    img = qr.make_image(fill_color="black", back_color="white")
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    b64 = _b64.b64encode(buf.getvalue()).decode("ascii")
                    payload["qr_base64"] = f"data:image/png;base64,{b64}"
                except Exception:
                    pass  # qrcode lib 未安装 → 前端用 qr_url 自行渲染
                loop.call_soon_threadsafe(
                    events_queue.put_nowait, ("qrcode", payload)
                )

            def _on_status_change(status: str) -> None:
                """SDK 回调 → 推 status 事件。"""
                mapped, message = status_map.get(
                    status, ("failed", f"未知状态: {status}")
                )
                loop.call_soon_threadsafe(
                    events_queue.put_nowait,
                    ("status", {"status": mapped, "message": message}),
                )

            def _do_login():
                """在 executor 线程中执行阻塞 login()。"""
                try:
                    from weixin_ilink import login  # lazy import
                    creds = login(
                        save_to=str(creds_path),
                        on_qrcode=_on_qrcode,
                        on_status_change=_on_status_change,
                    )
                    loop.call_soon_threadsafe(
                        events_queue.put_nowait, ("creds", creds)
                    )
                except Exception as e:
                    loop.call_soon_threadsafe(
                        events_queue.put_nowait, ("error", str(e))
                    )

            executor_future = loop.run_in_executor(None, _do_login)

            async def _send(event: str, data: dict):
                payload = json.dumps(data, ensure_ascii=False)
                await resp.write(
                    f"event: {event}\ndata: {payload}\n\n".encode("utf-8")
                )

            async def _heartbeat():
                """每 5s 发送心跳注释，防止代理超时断开。"""
                while True:
                    await asyncio.sleep(5)
                    try:
                        await resp.write(b": ping\n\n")
                    except Exception:
                        return

            heartbeat_task = asyncio.create_task(_heartbeat())
            login_succeeded = False
            try:
                while True:
                    event_type, payload = await events_queue.get()
                    if event_type == "qrcode":
                        await _send("qrcode", payload)
                    elif event_type == "status":
                        await _send("status", payload)
                    elif event_type == "creds":
                        await _send("done", {"ok": True})
                        login_succeeded = True
                        break
                    elif event_type == "error":
                        await _send("done", {"ok": False, "error": payload})
                        break
            except (ConnectionResetError, asyncio.CancelledError):
                pass
            except Exception as e:
                logger.error(f"WeChat SSE login error: {e}")
            finally:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass
                if not executor_future.done():
                    executor_future.cancel()
                try:
                    await resp.write_eof()
                except Exception:
                    pass
                # 登录成功后自动启动 WeChatAdapter，保持账户在线状态（长轮询维持会话）
                # 仅在 adapter_manager 已注入时执行；失败只 log warning，不影响 SSE 关闭
                if login_succeeded:
                    adapter_manager = getattr(app_components, "adapter_manager", None)
                    if adapter_manager is not None:
                        try:
                            from adapters.wechat import WeChatAdapter
                            # 已注册则先停止+注销旧的，避免重复（例如重复登录场景）
                            try:
                                existing = adapter_manager.get("wechat", account_id)
                                if existing is not None:
                                    await existing.stop()
                                    adapter_manager.unregister("wechat", account_id)
                            except Exception:
                                pass
                            adapter = WeChatAdapter(account_id=account_id)
                            # 注入 session_expired 回调（watchdog 触发后通知 WebUI）
                            adapter.on_session_expired = _make_session_expired_callback(account_id)
                            adapter_manager.register(adapter, account_id=account_id)
                            await adapter.start()
                            logger.info(f"WeChat SSE login: auto-started adapter for {account_id}")
                        except Exception as e:
                            logger.warning(
                                f"WeChat SSE login: auto-start failed for {account_id}: {e}"
                            )
                            try:
                                adapter_manager.unregister("wechat", account_id)
                            except Exception:
                                pass
            return resp

    @routes.post("/api/wechat/logout/{account_id}")
    async def wechat_logout(request):
        """删除凭证文件 + 停止适配器（若运行中）。未配置 → 404。"""
        account_id = request.match_info["account_id"]
        try:
            accounts = _get_wechat_accounts_config()
            if not any(a.get("id") == account_id for a in accounts):
                return web.json_response(
                    {"error": f"account not configured: {account_id}"}, status=404,
                )
            creds_path = _wechat_credentials_path(account_id)
            if creds_path.exists():
                creds_path.unlink()
            adapter_manager = getattr(app_components, "adapter_manager", None)
            if adapter_manager is not None:
                try:
                    adapter = adapter_manager.get("wechat", account_id)
                    if adapter is not None:
                        await adapter.stop()
                except Exception as e:
                    logger.warning(f"WeChat logout: failed to stop adapter: {e}")
            logger.info(f"WebUI wechat logout: {account_id}")
            return web.json_response({"ok": True})
        except Exception as e:
            logger.error(f"WebUI wechat_logout error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    @routes.get("/api/wechat/status/{account_id}")
    async def wechat_status(request):
        """返回账号登录状态。未配置 → 404。"""
        account_id = request.match_info["account_id"]
        try:
            accounts = _get_wechat_accounts_config()
            if not any(a.get("id") == account_id for a in accounts):
                return web.json_response(
                    {"error": f"account not configured: {account_id}"}, status=404,
                )
            creds_path = _wechat_credentials_path(account_id)
            adapter_running = False
            adapter_manager = getattr(app_components, "adapter_manager", None)
            if adapter_manager is not None:
                try:
                    adapter = adapter_manager.get("wechat", account_id)
                    adapter_running = adapter is not None
                except Exception:
                    adapter_running = False
            return web.json_response({
                "has_credentials": creds_path.exists(),
                "adapter_running": adapter_running,
            })
        except Exception as e:
            logger.error(f"WebUI wechat_status error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    @web.middleware
    async def friendly_error_middleware(request, handler):
        """Keep technical exception details in logs and out of user responses."""
        try:
            response = await handler(request)
        except web.HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Unhandled WebUI error on {request.method} {request.path}: {e}")
            return web.json_response(
                {"error": "服务暂时无法完成操作，请稍后重试"}, status=500,
            )
        if response.status >= 500 and response.content_type == "application/json":
            message = "功能暂时不可用，请稍后重试" if response.status == 503 else "服务暂时无法完成操作，请稍后重试"
            return web.json_response({"error": message}, status=response.status)
        return response

    aio_app = web.Application(
        client_max_size=512 * 1024 * 1024,
        middlewares=[friendly_error_middleware],
    )
    aio_app.add_routes(routes)
    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    aio_app.router.add_static("/avatars", AVATAR_DIR, name="avatars")
    if STATIC_DIR.exists():
        aio_app.router.add_static("/static/", STATIC_DIR, name="static")

    # T13: best-effort legacy web_user.json → web:default binding migration.
    # 失败不阻塞 server 启动（log warning + 继续）。
    try:
        migrate_legacy_web_user(
            getattr(app_components, "conversation_store", None), DATA_DIR
        )
    except Exception as e:
        logger.warning(f"T13 legacy migration failed: {e}")

    return aio_app


_whisper_model = None
_whisper_model_lock = threading.Lock()


def _get_whisper_model():
    """Load the optional local ASR model once per process.

    Loading Whisper for every voice request made the WebUI appear frozen for
    several seconds and repeatedly consumed memory. The model remains an
    optional fallback because browser speech recognition is the zero-install
    path for portable builds.
    """
    global _whisper_model
    if _whisper_model is not None:
        return _whisper_model
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except Exception:
        return None
    with _whisper_model_lock:
        if _whisper_model is None:
            model_name = os.getenv("CC_WHISPER_MODEL", "base")
            _whisper_model = WhisperModel(model_name, device="cpu", compute_type="int8")
    return _whisper_model


def _try_transcribe(audio_path: Path) -> str | None:
    """Try optional faster-whisper transcription; return None when unavailable."""
    try:
        model = _get_whisper_model()
        if model is None:
            return None
        segments, _info = model.transcribe(str(audio_path), language="zh")
        return "".join(seg.text for seg in segments).strip() or None
    except Exception as e:
        logger.warning(f"WebUI ASR failed: {e}")
        return None


# ===== TTS 语音回复 =====

TTS_AUDIO_DIR = DATA_DIR / "tts_audio"


def _tts_store() -> TTSStore:
    return TTSStore(CONFIG_DIR)


def _tts_manager() -> TTSManager:
    return TTSManager(_tts_store())


def _tts_cache_dir() -> Path:
    p = TTS_AUDIO_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def _serve_audio_bytes(request, data: bytes, content_type: str = "audio/mpeg"):
    """支持 HTTP Range 的音频响应（浏览器可拖动播放）。"""
    from aiohttp import web
    size = len(data)
    rng = request.headers.get("Range")
    if rng:
        try:
            start_s = rng.replace("bytes=", "").split("-")[0].strip()
            start = int(start_s) if start_s else 0
            end = size - 1
        except (ValueError, AttributeError):
            start, end = 0, size - 1
        if start >= size:
            return web.Response(status=416)
        body = data[start:end + 1]
        return web.Response(
            status=206,
            body=body,
            headers={
                "Content-Type": content_type,
                "Content-Range": f"bytes {start}-{end}/{size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(len(body)),
                "Cache-Control": "private, max-age=3600",
            },
        )
    return web.Response(
        body=data,
        headers={
            "Content-Type": content_type,
            "Accept-Ranges": "bytes",
            "Content-Length": str(size),
            "Cache-Control": "private, max-age=3600",
        },
    )


async def run_web(app_components, host: str = "127.0.0.1", port: int = 8000) -> None:
    """启动网页服务（阻塞直到取消）。"""
    from aiohttp import web

    # 确保 adapter_manager 存在（Web 模式不经过 run_with_adapters，需在此注入）
    if getattr(app_components, "adapter_manager", None) is None:
        from adapters import AdapterManager
        app_components.adapter_manager = AdapterManager()

    # 注入消息处理回调（Web 模式不经过 run_with_adapters，需在此注入）
    # 否则 adapter._handler 为 None，_on_inbound_message 会静默丢弃所有消息。
    # 依赖：pipeline（app.handler.pipeline）+ DebounceManager + make_message_handler
    adapter_manager = app_components.adapter_manager
    if not getattr(adapter_manager, "_message_handler", None):
        try:
            from adapters.debounce import DebounceManager
            from core.app import make_message_handler
            pipeline = app_components.handler.pipeline
            debounce_seconds = app_components.advanced_config.get("debounce_seconds", 3)
            debounce = DebounceManager(debounce_seconds, pipeline, app_components, adapter_manager)
            handler = make_message_handler(app_components, pipeline, debounce)
            adapter_manager.set_message_handler(handler)
            logger.info("WebUI: injected message handler + DebounceManager for adapters")
        except Exception as e:
            logger.warning(f"WebUI: inject message handler failed: {e}")

    aio_app = _make_app(app_components)
    runner = web.AppRunner(aio_app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()

    # 连接 MCP 工具（可选）
    mcp = getattr(app_components, "mcp_manager", None)
    if mcp is not None:
        try:
            connected = await mcp.load_and_connect(CONFIG_DIR)
            if connected:
                logger.info(f"WebUI: MCP {connected} server(s) connected")
        except Exception as e:
            logger.warning(f"WebUI: MCP connect failed: {e}")

    # 自动启动已配置且已有凭证的微信账号（auto_start=True）
    # 失败不阻塞 server 启动（best-effort，单账号失败只 log warning）
    try:
        await _autostart_wechat_adapters(app_components)
    except Exception as e:
        logger.warning(f"WebUI: wechat autostart failed: {e}")

    # 朋友圈自动发布器（AI 自动发朋友圈）：按配置定时为指定人设发布动态。
    # 独立后台任务，失败不阻塞 server 启动。配置存 settings.json。
    try:
        if getattr(app_components, "moments_poster", None) is None:
            def _moment_saver(moment: dict) -> dict:
                now = _moment_now_iso()
                record = {
                    "id": _new_moment_id(),
                    "author": moment.get("author", "") or "user",
                    "timestamp": now,
                    "text": (moment.get("text") or "").strip(),
                    "likes": [],
                    "replies": [],
                    "auto": bool(moment.get("auto")),
                }
                moments = _load_moments()
                moments.insert(0, record)
                _save_moments(moments)
                return record

            def _moment_poster_persona_name(persona_id: str) -> str:
                loader = getattr(app_components, "persona_loader", None)
                if loader is None:
                    return ""
                try:
                    p = loader.get(persona_id)
                    return getattr(p, "name", "") or ""
                except Exception:
                    return ""

            _llm = getattr(getattr(app_components, "registry", None), "get", lambda: None)()
            poster_gen = None
            if _llm is not None and hasattr(_llm, "chat"):
                async def _gen(system_prompt: str, user_prompt: str,
                               max_tokens: int = 120, temperature: float = 0.95) -> str:
                    resp = await _llm.chat(
                        messages=[{"role": "user", "content": user_prompt}],
                        system_prompt=system_prompt,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                    return getattr(resp, "content", "") or ""
            poster = MomentsAutoPoster(
                saver=_moment_saver,
                get_settings=_load_settings,
                generate_fn=poster_gen,
                persona_name_fn=_moment_poster_persona_name,
            )
            app_components.moments_poster = poster
            asyncio.get_running_loop().create_task(poster.run())
            logger.info("WebUI: moments auto-poster started")
    except Exception as e:
        logger.warning(f"WebUI: moments auto-poster start failed: {e}")

    url = f"http://{host}:{port}"
    print(f"\n  🌐 网页端已启动：{url}")
    print(f"  浏览器打开上面的地址即可对话 + 调参")
    print(f"  按 Ctrl+C 停止\n")
    logger.info(f"WebUI running on {url}")

    try:
        await asyncio.Event().wait()
    finally:
        # 停止所有适配器（微信长轮询等后台任务）
        adapter_manager = getattr(app_components, "adapter_manager", None)
        if adapter_manager is not None:
            try:
                await adapter_manager.stop_all()
            except Exception as e:
                logger.warning(f"WebUI: adapter stop_all failed: {e}")
        try:
            await app_components.handler.pipeline.shutdown()
        except Exception as e:
            logger.warning(f"WebUI: pipeline shutdown failed: {e}")
        await runner.cleanup()
