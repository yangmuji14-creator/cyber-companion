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


# 已知支持图片的多模态模型
MULTIMODAL_MODELS = {
    "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4-vision",
    "gpt-4-vision-preview",
    "claude-3", "claude-3-opus", "claude-3-sonnet", "claude-3-haiku",
    "claude-3-5-sonnet", "claude-3-5-haiku",
    "gemini-pro-vision", "gemini-1.5-pro", "gemini-1.5-flash",
    "gemini-2.0-flash",
    "qwen-vl", "qwen-vl-plus", "qwen-vl-max",
    "glm-4v",
    "llava", "bakllava",
}


def is_multimodal_model(model_name: str) -> bool:
    """检查模型是否支持图片输入"""
    if not model_name:
        return False
    model_lower = model_name.lower()
    for name in MULTIMODAL_MODELS:
        if name in model_lower:
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
            import litellm

            kwargs = {
                "model": f"{provider}/{model_name}" if provider else model_name,
                "messages": messages,
                "max_tokens": 1000,
            }
            if api_key:
                kwargs["api_key"] = api_key
            if base_url:
                kwargs["api_base"] = base_url

            response = await litellm.acompletion(**kwargs)
            description = response.choices[0].message.content

            logger.debug(f"Fallback vision result ({len(description)} chars)")
            return f"[图片描述] {description}"

        except ImportError:
            logger.error("litellm not available for vision fallback")
            return "[图片识别失败: litellm 未安装]"
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
