"""LLM 统一接口定义"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import litellm
from loguru import logger


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
        temperature: float = 0.8,
    ):
        self.model_name = model_name
        self.api_key = api_key
        self.base_url = base_url
        self.max_tokens = max_tokens
        self.temperature = temperature

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

        try:
            response = await litellm.acompletion(
                model=model_id,
                messages=full_messages,
                max_tokens=kwargs.pop("max_tokens", self.max_tokens),
                temperature=kwargs.pop("temperature", self.temperature),
                api_key=self.api_key,
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

        except Exception as e:
            logger.error(f"LLM call failed for {model_id}: {e}")
            raise
