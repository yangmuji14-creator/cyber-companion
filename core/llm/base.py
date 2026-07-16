"""LLM 统一接口定义 — v4.1 hardened"""

import asyncio
import os
import random
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

import litellm
from loguru import logger

# 可重试的 HTTP 状态码
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
# 不可重试的错误关键词（永久性错误）
_NON_RETRYABLE_KEYWORDS = {"auth", "401", "403", "api_key", "invalid_request", "insufficient_quota"}


@dataclass
class LLMResponse:
    """LLM 响应数据结构"""

    content: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseLLM(ABC):
    """大模型统一接口基类

    所有模型接入都继承此类，实现 chat 方法。
    使用 LiteLLM 作为底层统一调用层。
    """

    def __init__(
        self,
        model_name: str,
        api_key: str,
        base_url: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 1.0,
        max_retries: int = 2,
        presence_penalty: float = 0.3,   # 减少重复模式（如括号动作描写）
        frequency_penalty: float = 0.3,  # 同上
    ):
        self.model_name = model_name
        self.api_key = api_key
        self.base_url = base_url
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.max_retries = max_retries
        self.presence_penalty = presence_penalty
        self.frequency_penalty = frequency_penalty

    @staticmethod
    def _is_retryable(error: Exception) -> bool:
        """判断错误是否可重试（网络/超时/限流/服务端错误）"""
        error_str = str(error).lower()
        for kw in _NON_RETRYABLE_KEYWORDS:
            if kw in error_str:
                return False
        retryable_keywords = {"timeout", "connection", "connect", "rate", "429",
                              "500", "502", "503", "504", "eof", "reset",
                              "overloaded", "server error", "try again"}
        return any(kw in error_str for kw in retryable_keywords)

    async def _retry(self, coro_factory, operation_name: str):
        """带指数退避 + 随机抖动的重试包装器"""
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                return await coro_factory()
            except Exception as e:
                last_error = e
                if attempt < self.max_retries and self._is_retryable(e):
                    # 指数退避 + 随机抖动（避免惊群效应）
                    base_delay = 1.0 * (2 ** attempt)
                    jitter = random.uniform(0, base_delay * 0.5)
                    delay = base_delay + jitter
                    logger.warning(
                        f"{operation_name} failed (attempt {attempt + 1}/{self.max_retries + 1}): {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    break
        raise last_error

    def _resolve_api_key(self, model_id: str) -> str:
        """解析 API key：实例属性 > 环境变量"""
        if self.api_key:
            return self.api_key
        prefix = model_id.split("/")[0].upper()
        return os.environ.get(f"{prefix}_API_KEY", "")

    def _litellm_kwargs(self, kwargs: dict) -> dict:
        """构建 litellm 参数，从 kwargs 中取出已知键（pop 避免重复传参）。

        注意：必须用 pop() 而非 get()，否则调用方再展开 **kwargs 时
        会把同一个参数（如 max_tokens）传两次，导致 litellm 报
        "got multiple values for keyword argument 'max_tokens'"。
        pop 后，调用方用 **kwargs 透传剩余的未知参数（如 stream、tools）。
        """
        return {
            "max_tokens": kwargs.pop("max_tokens", self.max_tokens),
            "temperature": kwargs.pop("temperature", self.temperature),
            "presence_penalty": kwargs.pop("presence_penalty", self.presence_penalty),
            "frequency_penalty": kwargs.pop("frequency_penalty", self.frequency_penalty),
            "timeout": kwargs.pop("timeout", 120),  # 默认 120s 超时
        }

    @abstractmethod
    def _build_model_id(self) -> str:
        """构建 LiteLLM 格式的 model ID，如 'deepseek/deepseek-chat'"""
        ...

    async def chat(
        self,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
        **kwargs,
    ) -> LLMResponse:
        """统一聊天接口

        Args:
            messages: 消息列表，格式 [{"role": "user", "content": "..."}]
            system_prompt: 系统提示词（可选，也可直接放在 messages 里）
            **kwargs: 传递给 LiteLLM 的额外参数

        Returns:
            LLMResponse 包含回复内容和元数据
        """
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        model_id = self._build_model_id()
        logger.debug(f"Calling {model_id} with {len(full_messages)} messages")

        async def _do_call():
            response = await litellm.acompletion(
                model=model_id,
                messages=full_messages,
                api_key=self._resolve_api_key(model_id),
                base_url=self.base_url,
                **self._litellm_kwargs(kwargs),
                **kwargs,  # 用户自定义覆盖参数
            )

            content = response.choices[0].message.content or ""
            usage = {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            }
            if response.usage:
                for field_name in (
                    "cache_creation_input_tokens",
                    "cache_read_input_tokens",
                ):
                    field_value = getattr(response.usage, field_name, None)
                    if field_value is not None:
                        usage[field_name] = field_value

                prompt_details = getattr(response.usage, "prompt_tokens_details", None)
                cached_tokens = getattr(prompt_details, "cached_tokens", None)
                if cached_tokens is not None:
                    usage["cached_tokens"] = cached_tokens

            logger.info(
                f"{model_id} responded: {len(content)} chars, "
                f"{usage['total_tokens']} tokens, "
                f"cache read/hit: {usage.get('cache_read_input_tokens', 0)}/"
                f"{usage.get('cached_tokens', 0)} tokens"
            )

            return LLMResponse(
                content=content,
                model=model_id,
                usage=usage,
                metadata={"finish_reason": response.choices[0].finish_reason},
            )

        try:
            return await self._retry(_do_call, f"chat({model_id})")
        except Exception as e:
            logger.error(f"LLM call failed for {model_id}: {e}")
            raise

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        system_prompt: str | None = None,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        """流式聊天接口 — 逐 token yield 回复内容

        流式调用在开始 yield 前支持重试（连接阶段），
        一旦开始输出 token，错误直接抛出（无法部分重试）。

        Args:
            messages: 消息列表，格式 [{"role": "user", "content": "..."}]
            system_prompt: 系统提示词（可选）
            **kwargs: 传递给 LiteLLM 的额外参数

        Yields:
            每个 token 片段
        """
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        model_id = self._build_model_id()
        logger.debug(f"Calling {model_id} (stream) with {len(full_messages)} messages")

        last_error = None
        yielded_any = False
        for attempt in range(self.max_retries + 1):
            try:
                # 每次调用重新读 env
                response = await litellm.acompletion(
                    model=model_id,
                    messages=full_messages,
                    api_key=self._resolve_api_key(model_id),
                    base_url=self.base_url,
                    stream=True,
                    **self._litellm_kwargs(kwargs),
                    **kwargs,
                )

                async for chunk in response:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        yielded_any = True
                        yield delta.content
                return  # 成功完成，直接返回

            except Exception as e:
                if yielded_any:
                    raise
                last_error = e
                if attempt < self.max_retries and self._is_retryable(e):
                    delay = 1.0 * (2 ** attempt)
                    logger.warning(
                        f"stream({model_id}) failed (attempt {attempt + 1}): {e}. "
                        f"Retrying in {delay:.0f}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    break

        logger.error(f"LLM stream call failed for {model_id}: {last_error}")
        raise last_error
