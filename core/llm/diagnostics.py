"""Provider-agnostic connectivity checks for onboarding and diagnostics."""

from __future__ import annotations

import asyncio
from time import monotonic
from urllib.parse import urlsplit

import aiohttp


def _chat_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    return base if base.endswith("/chat/completions") else f"{base}/chat/completions"


def _safe_host(base_url: str) -> str:
    try:
        return urlsplit(base_url).hostname or "服务地址"
    except ValueError:
        return "服务地址"


async def discover_models(*, base_url: str, api_key: str, timeout_seconds: float = 15.0) -> dict[str, object]:
    """Discover model ids through the local backend, keeping API keys out of the browser."""
    base_url, api_key = (base_url or "").strip().rstrip("/"), (api_key or "").strip()
    if not base_url or not api_key:
        return {"ok": False, "code": "missing_fields", "message": "请填写 API 地址和密钥"}
    parsed = urlsplit(base_url)
    if not parsed.scheme or not parsed.netloc:
        return {"ok": False, "code": "invalid_url", "message": "API 地址格式不正确"}
    url = base_url if base_url.endswith("/models") else f"{base_url}/models"
    timeout = aiohttp.ClientTimeout(total=max(3.0, timeout_seconds))
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as response:
                if response.status in {401, 403}:
                    return {"ok": False, "code": "auth", "message": "API 密钥无效或没有模型列表权限"}
                if response.status == 404:
                    return {"ok": False, "code": "endpoint", "message": f"{_safe_host(base_url)} 没有找到模型列表接口"}
                if response.status == 429:
                    return {"ok": False, "code": "rate_limited", "message": "服务商暂时限流，可以稍后重试"}
                if response.status >= 400:
                    return {"ok": False, "code": "request", "message": "无法读取模型列表，请检查 API 地址"}
                body = await response.json(content_type=None)
                raw = body.get("data", []) if isinstance(body, dict) else []
                models = sorted({str(item.get("id", "")).strip() for item in raw if isinstance(item, dict) and item.get("id")})[:200]
                if not models:
                    return {"ok": False, "code": "empty", "message": "服务商没有返回可用模型，请手动填写模型 ID"}
                return {"ok": True, "code": "ok", "message": f"已找到 {len(models)} 个模型", "models": models}
    except asyncio.TimeoutError:
        return {"ok": False, "code": "timeout", "message": "读取模型列表超时，请检查网络"}
    except aiohttp.ClientConnectorError:
        return {"ok": False, "code": "network", "message": f"无法连接 {_safe_host(base_url)}，请检查网络或代理设置"}
    except (aiohttp.InvalidURL, ValueError):
        return {"ok": False, "code": "invalid_url", "message": "API 地址格式不正确"}
    except Exception:
        return {"ok": False, "code": "unknown", "message": "读取模型列表失败，请手动填写模型 ID"}


async def test_provider_connection(*, base_url: str, api_key: str, model_name: str, timeout_seconds: float = 20.0) -> dict[str, object]:
    """Send a minimal request and return a redacted, user-facing result."""
    base_url, api_key, model_name = (base_url or "").strip().rstrip("/"), (api_key or "").strip(), (model_name or "").strip()
    if not base_url or not api_key or not model_name:
        return {"ok": False, "code": "missing_fields", "message": "请填写 API 地址、密钥和模型名称"}
    parsed = urlsplit(base_url)
    if not parsed.scheme or not parsed.netloc:
        return {"ok": False, "code": "invalid_url", "message": "API 地址格式不正确"}

    payload = {"model": model_name, "messages": [{"role": "user", "content": "请只回复 OK"}], "max_tokens": 8, "temperature": 0, "stream": False}
    started = monotonic()
    timeout = aiohttp.ClientTimeout(total=max(3.0, timeout_seconds))
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(_chat_url(base_url), json=payload, headers=headers) as response:
                elapsed = round((monotonic() - started) * 1000)
                if response.status in {401, 403}:
                    return {"ok": False, "code": "auth", "message": "API 密钥无效或没有该模型的权限", "latency_ms": elapsed}
                if response.status == 404:
                    return {"ok": False, "code": "endpoint", "message": f"{_safe_host(base_url)} 没有找到聊天接口，请检查 API 地址", "latency_ms": elapsed}
                if response.status == 429:
                    return {"ok": False, "code": "rate_limited", "message": "服务商暂时限流，可以稍后重试", "latency_ms": elapsed}
                if response.status >= 500:
                    return {"ok": False, "code": "provider_error", "message": "服务商暂时忙碌，请稍后重试", "latency_ms": elapsed}
                if response.status >= 400:
                    return {"ok": False, "code": "request", "message": "模型或请求参数不被服务商接受，请检查模型名称", "latency_ms": elapsed}
                body = await response.json(content_type=None)
                if not isinstance(body, dict) or not body.get("choices"):
                    return {"ok": False, "code": "empty_response", "message": "服务商响应为空，请检查模型名称", "latency_ms": elapsed}
                return {"ok": True, "code": "ok", "message": "连接成功，可以开始聊天", "latency_ms": elapsed}
    except asyncio.TimeoutError:
        return {"ok": False, "code": "timeout", "message": "连接等待超时，请检查网络或更换服务商"}
    except aiohttp.ClientConnectorError:
        return {"ok": False, "code": "network", "message": f"无法连接 {_safe_host(base_url)}，请检查网络或代理设置"}
    except (aiohttp.InvalidURL, ValueError):
        return {"ok": False, "code": "invalid_url", "message": "API 地址格式不正确"}
    except Exception:
        return {"ok": False, "code": "unknown", "message": "连接失败，请检查 API 地址、密钥和网络"}
