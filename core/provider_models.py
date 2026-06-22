"""厂商模型列表查询模块

用于 setup 向导中「获取 API Key → 拉取可用模型 → 让用户选择」流程。
每个厂商定义了：
  - API 端点：通过 HTTP GET 获取模型列表
  - 解析器：从响应中提取模型 ID
  - 过滤器：自动过滤出有意义的聊天模型（如 OpenAI 几百个模型只留 gpt/o 系列）
  - 兜底列表：API 不可达/超时/Key 无效时使用
"""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from typing import Callable

# ──────────────────────────────────────────────
# 厂商模型列表 API 定义
# ──────────────────────────────────────────────

ProviderApiDef = dict[str, dict]

PROVIDER_APIS: ProviderApiDef = {
    "deepseek": {
        "url": "https://api.deepseek.com/models",
        "headers_fn": lambda key: {"Authorization": f"Bearer {key}"},
        "parse": lambda data: [m["id"] for m in data.get("data", [])],
        "filter": None,  # DeepSeek 返回的就是聊天模型
        "fallback": ["deepseek-chat", "deepseek-reasoner"],
    },
    "openai": {
        "url": "https://api.openai.com/v1/models",
        "headers_fn": lambda key: {"Authorization": f"Bearer {key}"},
        "parse": lambda data: [m["id"] for m in data.get("data", [])],
        "filter": lambda models: [
            m for m in models
            if m.startswith(("gpt-", "o")) and "realtime" not in m and "instruct" not in m
        ],
        "fallback": ["gpt-4o-mini", "gpt-4o", "o3-mini", "gpt-4.1-mini"],
    },
    "gemini": {
        "url": "https://generativelanguage.googleapis.com/v1/models",
        "headers_fn": lambda key: {},  # Gemini 用 query param
        "parse": lambda data: [
            m["name"].replace("models/", "")
            for m in data.get("models", [])
            if any(
                s.get("name", "").endswith("generateContent")
                for s in m.get("supportedGenerationMethods", [])
            )
        ],
        "filter": None,
        "fallback": ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-pro"],
    },
    "qwen": {
        "url": "https://dashscope.aliyuncs.com/compatible-mode/v1/models",
        "headers_fn": lambda key: {
            "Authorization": f"Bearer {key}",
        },
        "parse": lambda data: [m["id"] for m in data.get("data", [])],
        "filter": lambda models: [
            m for m in models
            if "qwen" in m.lower() or "qwq" in m.lower() or "qvq" in m.lower()
        ],
        "fallback": ["qwen-turbo", "qwen-plus", "qwen-max"],
    },
    "kimi": {
        "url": "https://api.moonshot.cn/v1/models",
        "headers_fn": lambda key: {"Authorization": f"Bearer {key}"},
        "parse": lambda data: [m["id"] for m in data.get("data", [])],
        "filter": None,
        "fallback": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
    },
    "zhipu": {
        "url": "https://open.bigmodel.cn/api/paas/v4/models",
        "headers_fn": lambda key: {"Authorization": f"Bearer {key}"},
        "parse": lambda data: [m["id"] for m in data.get("data", [])],
        "filter": None,
        "fallback": ["glm-4-flash", "glm-4-plus", "glm-4-air", "glm-4-0520"],
    },
}

# ──────────────────────────────────────────────
# 公开接口
# ──────────────────────────────────────────────


def get_provider_config(provider_key: str) -> dict | None:
    """获取厂商的 API 配置"""
    return PROVIDER_APIS.get(provider_key)


def get_fallback_models(provider_key: str) -> list[str]:
    """获取指定厂商的兜底模型列表（API 不可用时使用）"""
    cfg = PROVIDER_APIS.get(provider_key)
    return cfg["fallback"] if cfg else []


def fetch_models(
    provider_key: str,
    api_key: str,
    base_url: str | None = None,
    timeout: int = 8,
) -> list[str] | None:
    """实时拉取指定厂商的可用模型列表

    参数:
        provider_key: 厂商标识（deepseek / openai / gemini / qwen / kimi / zhipu）
        api_key: 用户的 API Key
        base_url: 可选的 Base URL 覆盖（如用户自建代理）
        timeout: 超时秒数

    返回:
        模型 ID 列表（已过滤），拉取失败时返回 None
    """
    cfg = PROVIDER_APIS.get(provider_key)
    if not cfg:
        return None

    url = base_url.rstrip("/") + "/models" if base_url else cfg["url"]

    # Gemini 用 query parameter 传 Key
    if provider_key == "gemini":
        url = cfg["url"]
        if api_key:
            url += f"?key={api_key}"

    headers = cfg["headers_fn"](api_key)

    try:
        req = urllib.request.Request(url, headers=headers, method="GET")
        ctx = ssl.create_default_context()
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED

        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw)

        models = cfg["parse"](data)
        if cfg.get("filter"):
            models = cfg["filter"](models)

        return sorted(set(models)) if models else None

    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError,
            TimeoutError, OSError):
        return None


def fetch_or_fallback(
    provider_key: str,
    api_key: str,
    base_url: str | None = None,
    timeout: int = 8,
) -> list[str]:
    """尝试拉取模型列表，失败时返回兜底列表

    返回的列表必定非空。
    """
    models = fetch_models(provider_key, api_key, base_url, timeout)
    if models:
        return models
    return get_fallback_models(provider_key)
