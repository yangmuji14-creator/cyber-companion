"""LLM 统一接口定义"""

import asyncio
import os
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import litellm
from loguru import logger

# 可重试的 HTTP 状态码
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
# 不可重试的错误关键词（永久性错误）
_NON_RETRYABLE_KEYWORDS = {"auth", "401", "403", "api_key", "invalid_request"}


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
        # 永久性错误不重试
        for kw in _NON_RETRYABLE_KEYWORDS:
            if kw in error_str:
                return False
        # 可重试的错误
        retryable_keywords = {"timeout", "connection", "connect", "rate", "429",
                              "500", "502", "503", "504", "eof", "reset"}
        return any(kw in error_str for kw in retryable_keywords)

    async def _retry(self, coro_factory, operation_name: str):
        """带指数退避的重试包装器

        Args:
            coro_factory: 无参数的协程工厂函数（每次重试创建新协程）
            operation_name: 操作名称（用于日志）

        Returns:
            协程执行结果

        Raises:
            最后一次重试仍然失败时抛出原始异常
        """
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                return await coro_factory()
            except Exception as e:
                last_error = e
                if attempt < self.max_retries and self._is_retryable(e):
                    delay = 1.0 * (2 ** attempt)  # 1s, 2s
                    logger.warning(
                        f"{operation_name} failed (attempt {attempt + 1}/{self.max_retries + 1}): {e}. "
                        f"Retrying in {delay:.0f}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    break
        raise last_error

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
            # 每次调用重新读 env（视觉调用可能污染 os.environ）
            _key = self.api_key
            if not _key:
                _key = os.environ.get(f"{self._build_model_id().split('/')[0].upper()}_API_KEY", "")
            response = await litellm.acompletion(
                model=model_id,
                messages=full_messages,
                max_tokens=kwargs.pop("max_tokens", self.max_tokens),
                temperature=kwargs.pop("temperature", self.temperature),
                presence_penalty=kwargs.pop("presence_penalty", self.presence_penalty),
                frequency_penalty=kwargs.pop("frequency_penalty", self.frequency_penalty),
                api_key=_key,
                base_url=self.base_url,
                **kwargs,
            )

            content = response.choices[0].message.content or ""
            usage = {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            }

            logger.info(
                f"{model_id} responded: {len(content)} chars, "
                f"{usage['total_tokens']} tokens"
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
        for attempt in range(self.max_retries + 1):
            try:
                # 每次调用重新读 env
                _key = self.api_key
                if not _key:
                    _key = os.environ.get(f"{model_id.split('/')[0].upper()}_API_KEY", "")
                response = await litellm.acompletion(
                    model=model_id,
                    messages=full_messages,
                    max_tokens=kwargs.pop("max_tokens", self.max_tokens),
                    temperature=kwargs.pop("temperature", self.temperature),
                    presence_penalty=kwargs.pop("presence_penalty", self.presence_penalty),
                    frequency_penalty=kwargs.pop("frequency_penalty", self.frequency_penalty),
                    api_key=_key,
                    base_url=self.base_url,
                    stream=True,
                    **kwargs,
                )

                async for chunk in response:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        yield delta.content
                return  # 成功完成，直接返回

            except Exception as e:
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
