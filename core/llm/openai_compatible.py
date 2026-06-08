"""OpenAI 兼容接口 - 适用于大多数国产模型"""

from .base import BaseLLM


class OpenAICompatibleLLM(BaseLLM):
    """OpenAI 兼容接口

    适用于：OpenAI、通义千问(兼容模式)、Kimi、智谱、以及任何兼容 OpenAI API 格式的模型。
    通过 base_url 区分不同服务商。
    """

    def _build_model_id(self) -> str:
        # LiteLLM 对 OpenAI 兼容接口使用 openai/ 前缀
        return f"openai/{self.model_name}"
