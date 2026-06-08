"""DeepSeek 模型接入"""

from .base import BaseLLM


class DeepSeekLLM(BaseLLM):
    """DeepSeek 大模型接入

    DeepSeek API 兼容 OpenAI 格式，使用 LiteLLM 的 deepseek/ 前缀。
    """

    def _build_model_id(self) -> str:
        return f"deepseek/{self.model_name}"
