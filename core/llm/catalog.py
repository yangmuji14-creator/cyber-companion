"""User-facing model provider catalog.

The catalog is data-driven so adding a provider does not require changing the
WebUI onboarding flow.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ProviderSpec:
    key: str
    label: str
    description: str
    base_url: str
    default_model: str
    env_key: str
    provider: str = "openai"

    def public_dict(self) -> dict[str, str]:
        return asdict(self)


PROVIDER_CATALOG: tuple[ProviderSpec, ...] = (
    ProviderSpec("deepseek", "DeepSeek", "国内访问稳定，适合日常聊天", "https://api.deepseek.com/v1", "deepseek-chat", "DEEPSEEK_API_KEY", provider="deepseek"),
    ProviderSpec("qwen", "通义千问", "国内服务，支持多种模型", "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-turbo", "TONGYI_API_KEY"),
    ProviderSpec("zhipu", "智谱 GLM", "国内服务，有免费体验额度", "https://open.bigmodel.cn/api/paas/v4", "glm-4-flash", "ZHIPU_API_KEY"),
    ProviderSpec("kimi", "Kimi", "长上下文对话，国内服务", "https://api.moonshot.cn/v1", "moonshot-v1-8k", "KIMI_API_KEY"),
    ProviderSpec("openai", "OpenAI", "需要可用的海外网络环境", "https://api.openai.com/v1", "gpt-4o-mini", "OPENAI_API_KEY"),
)


def get_provider_spec(key: str) -> ProviderSpec | None:
    return next((item for item in PROVIDER_CATALOG if item.key == key), None)


def public_provider_catalog() -> list[dict[str, str]]:
    return [item.public_dict() for item in PROVIDER_CATALOG]

