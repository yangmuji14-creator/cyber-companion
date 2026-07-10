"""LLM 注册中心 - 管理和切换不同模型"""

import json
import os
from pathlib import Path

from loguru import logger

from .base import BaseLLM
from .deepseek import DeepSeekLLM
from .openai_compatible import OpenAICompatibleLLM


# 模型 provider 到 LLM 类的映射
PROVIDER_MAP: dict[str, type[BaseLLM]] = {
    "deepseek": DeepSeekLLM,
    "openai": OpenAICompatibleLLM,
}


class LLMRegistry:
    """LLM 注册中心，负责加载配置、实例化和管理所有模型"""

    def __init__(self, config_path: str | Path | None = None):
        self._models: dict[str, BaseLLM] = {}
        self._default_model: str | None = None
        self._config: dict = {}

        if config_path:
            self.load_config(config_path)

    def load_config(self, config_path: str | Path) -> None:
        """从 settings.json 加载模型配置"""
        path = Path(config_path)
        if not path.exists():
            logger.warning(f"Config file not found: {path}")
            return

        with open(path, "r", encoding="utf-8") as f:
            self._config = json.load(f)

        self._default_model = self._config.get("default_model")
        models_config = self._config.get("models", {})

        for name, cfg in models_config.items():
            self._register_from_config(name, cfg)

        logger.info(
            f"Loaded {len(self._models)} models, default: {self._default_model}"
        )

    def _register_from_config(self, name: str, cfg: dict) -> None:
        """根据配置注册一个模型"""
        provider = cfg.get("provider", "openai")
        model_name = cfg.get("model_name", "")

        # 从环境变量读取 API Key
        env_key_map = {
            "deepseek": "DEEPSEEK_API_KEY",
            "openai": "OPENAI_API_KEY",
            "gemini": "GEMINI_API_KEY",
            "qwen": "TONGYI_API_KEY",
            "kimi": "KIMI_API_KEY",
            "zhipu": "ZHIPU_API_KEY",
            "mimo": "OPENAI_API_KEY",
            "doubao": "OPENAI_API_KEY",
            "baichuan": "OPENAI_API_KEY",
            "minimax": "OPENAI_API_KEY",
            "stepfun": "OPENAI_API_KEY",
            "moonshot": "OPENAI_API_KEY",
        }
        env_key = env_key_map.get(name, f"{name.upper()}_API_KEY")
        api_key = os.getenv(env_key, "")

        if not api_key:
            logger.warning(f"No API key found for {name} (env: {env_key}), skipping")
            return

        base_url = cfg.get("base_url")
        # 对于 openai provider，也从环境变量读 base_url
        if not base_url and provider == "openai":
            base_url = os.getenv(f"{name.upper()}_BASE_URL")

        llm_cls = PROVIDER_MAP.get(provider, OpenAICompatibleLLM)
        max_retries = self._config.get("advanced", {}).get("max_retries", 2)
        llm = llm_cls(
            model_name=model_name,
            api_key=api_key,
            base_url=base_url,
            max_tokens=cfg.get("max_tokens", 2048),
            temperature=cfg.get("temperature", 1.0),
            max_retries=max_retries,
            presence_penalty=cfg.get("presence_penalty", 0.3),
            frequency_penalty=cfg.get("frequency_penalty", 0.3),
        )
        self._models[name] = llm
        logger.debug(f"Registered model: {name} ({provider}/{model_name})")

    def register(self, name: str, llm: BaseLLM) -> None:
        """手动注册一个模型实例"""
        self._models[name] = llm

    def get(self, name: str | None = None) -> BaseLLM:
        """获取模型实例，默认返回 default_model"""
        target = name or self._default_model
        if not target or target not in self._models:
            available = list(self._models.keys())
            raise ValueError(
                f"Model '{target}' not found. Available: {available}"
            )
        return self._models[target]

    @property
    def available_models(self) -> list[str]:
        return list(self._models.keys())

    @property
    def default_model(self) -> str | None:
        return self._default_model


# 全局单例
_registry: LLMRegistry | None = None


def get_llm(name: str | None = None) -> BaseLLM:
    """快捷函数：获取全局注册中心中的模型"""
    global _registry
    if _registry is None:
        _registry = LLMRegistry()
    return _registry.get(name)


def init_registry(config_path: str | Path) -> LLMRegistry:
    """初始化全局注册中心"""
    global _registry
    _registry = LLMRegistry(config_path)
    return _registry
