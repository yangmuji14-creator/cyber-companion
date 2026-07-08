"""Vision Manager — 双路径图片识别

路径A（多模态模型）：将图片直接发送给主模型
路径B（文本模型）：将图片发送给视觉模型获取文字描述，再结合用户文本发送给主模型

配置（settings.json advanced 段）:
    "vision_model": {
        "provider": "openai",        // 视觉模型提供商
        "model_name": "gpt-4o",      // 模型名
        "api_key": "sk-xxx",          // API key（不填用环境变量）
        "base_url": ""                // 自定义 endpoint（可选）
    }

用法:
    vm = VisionManager(main_model, vision_config)
    result = await vm.process("/path/to/image.jpg", "这张图里有什么？")
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any

from loguru import logger


# 已知支持图片的多模态模型（持续更新）
# 匹配方式：model_name.lower() 包含这些字符串即判定为多模态
MULTIMODAL_PATTERNS = (
    # OpenAI
    "gpt-4o", "gpt-4-turbo", "gpt-4-vision", "o1", "o3",
    # Anthropic
    "claude-3", "claude-3-5", "claude-4",
    # Google
    "gemini-1.5", "gemini-2.0", "gemini-pro-vision", "gemini-flash",
    # Qwen / 通义千问
    "qwen-vl", "qwen2-vl", "qwen2.5-vl",
    # GLM / 智谱
    "glm-4v", "cogview", "cogvideox",
    # 开源模型
    "llava", "bakllava", "llama-3.2-vision", "llama-v", "pixtral",
    "internvl", "internlm-xcomposer", "minicpm-v", "cogvlm",
    # 小米 MiMo
    "mimo-v2.5", "mimo-v2",
    # 公司
    "doubao-vision", "doubao-1.5-vision",
    # 百川
    "baichuan-vl",
    # 零一万物
    "yi-vision", "yi-vl",
    # DeepSeek（注意：DeepSeek-VL2 支持视觉，但 DeepSeek-V3/Chat 不支持）
    "deepseek-vl",
    # 其他
    "step-1v", "step-1o-vision", "hunyuan-vision", "minimax-vl",
    "kimi-vl", "moonshot-vl",
)

# 明确不支持的模型（避免误判）
NOT_MULTIMODAL = (
    "deepseek-chat", "deepseek-reasoner", "deepseek-v3",
    "gpt-3.5", "gpt-3.5-turbo",
    "claude-2", "claude-instant",
    "mimo-v2.5-pro",  # MiMo Pro 是纯文本，只有 V2.5 支持多模态
)


def is_multimodal_model(model_name: str) -> bool:
    """检测模型是否支持图片输入

    检测顺序：
    1. 先查 litellm model_cost 中的 input_cost_per_image 标记
    2. 匹配已知多模态模型列表
    3. 排除明确不支持的模型

    Returns:
        True 如果模型支持图片
    """
    if not model_name:
        return False

    model_lower = model_name.lower()

    # 1. 排除明确不支持的模型
    for pattern in NOT_MULTIMODAL:
        if pattern in model_lower:
            return False

    # 2. 检查 litellm model info（有 input_cost_per_image 说明支持）
    try:
        import litellm
        info = litellm.get_model_info(model_name, ignore_HF_hub=True)
        if info and isinstance(info, dict):
            if info.get("input_cost_per_image") or info.get("input_cost_per_image_token"):
                return True
            if info.get("supports_vision") or info.get("supports_vision", False):
                return True
    except Exception:
        pass

    # 3. 匹配已知多模态模型
    for pattern in MULTIMODAL_PATTERNS:
        if pattern.lower() in model_lower:
            return True

    return False


def encode_image(image_path: str | Path) -> tuple[str, str]:
    """将图片编码为 base64 data URL

    Returns:
        (data_url, mime_type)
    """
    path = Path(image_path)
    mime_type, _ = mimetypes.guess_type(str(path))
    if not mime_type or not mime_type.startswith("image/"):
        mime_type = "image/png"  # 默认

    with open(path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")

    data_url = f"data:{mime_type};base64,{encoded}"
    return data_url, mime_type


class VisionManager:
    """双路径图片识别管理器"""

    def __init__(
        self,
        main_model: Any = None,           # litellm 模型实例
        vision_config: dict | None = None,  # settings.json vision_model 配置
    ):
        self._main_model = main_model
        self._vision_config = vision_config or {}
        self._vision_enabled = bool(self._vision_config.get("model_name"))

        if self._vision_enabled:
            logger.info(
                f"Vision fallback enabled: "
                f"{self._vision_config.get('provider')}/{self._vision_config.get('model_name')}"
            )

    @property
    def main_is_multimodal(self) -> bool:
        """主模型是否支持图片"""
        if not self._main_model:
            return False
        model_name = getattr(self._main_model, "model_name", "")
        return is_multimodal_model(model_name)

    # ── 路由 ──

    async def process(
        self,
        image_path: str | Path,
        user_text: str = "请描述这张图片的内容",
    ) -> str:
        """处理图片识别请求

        Args:
            image_path: 图片路径
            user_text: 用户对图片的附加问题

        Returns:
            图片描述文本
        """
        if not Path(image_path).exists():
            return f"[图片不存在: {image_path}]"

        # 路径A：主模型支持多模态 → 直接发送
        if self.main_is_multimodal and self._main_model:
            logger.info(f"Vision: using main model (multimodal) for {image_path}")
            return await self._direct_vision(image_path, user_text)

        # 路径B：使用独立的视觉模型
        if self._vision_enabled:
            logger.info(f"Vision: using fallback model for {image_path}")
            return await self._fallback_vision(image_path, user_text)

        # 都不行
        logger.warning(f"Vision: no model available for {image_path}")
        return ("[图片识别未配置] 当前模型不支持图片识别，且未配置视觉降级模型。\n"
                "请在 settings.json → advanced → vision_model 中配置视觉模型。")

    # ── 路径A：直传 ──

    async def _direct_vision(self, image_path: str | Path, user_text: str) -> str:
        """将图片直接发送给多模态主模型"""
        data_url, mime_type = encode_image(image_path)

        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": user_text or "请描述这张图片"},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }]

        try:
            if hasattr(self._main_model, "chat"):
                response = await self._main_model.chat(messages=messages)
                return response.content if hasattr(response, "content") else str(response)
            else:
                # 使用 litellm 直接调用
                import litellm
                model_name = getattr(self._main_model, "model_name", "gpt-4o")
                response = await litellm.acompletion(
                    model=model_name,
                    messages=messages,
                    max_tokens=1000,
                )
                return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Direct vision failed: {e}")
            return await self._fallback_vision(image_path, user_text)

    # ── 路径B：降级 ──

    async def _fallback_vision(self, image_path: str | Path, user_text: str) -> str:
        """使用独立视觉模型获取描述"""
        data_url, mime_type = encode_image(image_path)

        vision_cfg = self._vision_config
        provider = vision_cfg.get("provider", "openai")
        model_name = vision_cfg.get("model_name", "gpt-4o")
        base_url = vision_cfg.get("base_url", "")
        api_key = vision_cfg.get("api_key", "")

        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": user_text or "请详细描述这张图片的内容"},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }]

        try:
            import os

            # 用独立 OpenAI client 调用，彻底隔离 API key
            try:
                from openai import AsyncOpenAI
            except ImportError:
                from openai import OpenAI as _OpenAI
                AsyncOpenAI = None

            actual_base = base_url or "https://api.openai.com/v1"
            actual_key = api_key or os.environ.get("OPENAI_API_KEY", "")

            if AsyncOpenAI:
                client = AsyncOpenAI(api_key=actual_key, base_url=actual_base)
                response = await client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    max_tokens=1000,
                )
                description = response.choices[0].message.content
            else:
                # 降级到 litellm（旧版本 openai 库）
                import litellm
                response = await litellm.acompletion(
                    model=f"openai/{model_name}",
                    messages=messages,
                    api_key=actual_key,
                    api_base=actual_base,
                    max_tokens=1000,
                )
                description = response.choices[0].message.content

            logger.debug(f"Fallback vision result ({len(description)} chars)")

            # 暴力重置 litellm 全局状态 + 重新加载 .env
            try:
                import litellm
                litellm.api_key = None
                litellm.api_base = None
                litellm._async_client_cleanup_registered = False
            except Exception:
                pass

            # 重新加载 .env — 某些库（litellm/openai）可能覆盖了环境变量
            try:
                from dotenv import load_dotenv
                load_dotenv(override=True)
            except Exception:
                pass

            return f"[图片描述] {description}"

        except ImportError:
            logger.error("openai package not available for vision fallback")
            return "[图片识别失败: openai 未安装，请 pip install openai]"
        except Exception as e:
            logger.error(f"Fallback vision failed: {e}")
            return f"[图片识别失败: {e}]"

    # ── 辅助：为 Pipeline 构造带图片描述的增强消息 ──

    def build_enhanced_message(
        self,
        vision_result: str,
        user_text: str,
    ) -> str:
        """将视觉模型的输出和用户文本组合为增强消息

        路径B 使用此方法：视觉描述 + 用户文字 → 发送给文本模型

        Args:
            vision_result: 视觉模型返回的图片描述
            user_text: 用户的原始文字输入

        Returns:
            组合后的消息文本
        """
        if user_text:
            return (
                f"[用户发来了一张图片，以下是图片的详细描述：]\n"
                f"{vision_result}\n\n"
                f"[用户对这张图片的附加说明：]\n"
                f"{user_text}\n\n"
                f"请根据以上图片描述和用户的问题，自然地回复用户。"
            )
        else:
            return (
                f"[用户发来了一张图片，以下是图片的详细描述：]\n"
                f"{vision_result}\n\n"
                f"请根据以上图片描述，自然地与用户讨论这张图片。"
            )
