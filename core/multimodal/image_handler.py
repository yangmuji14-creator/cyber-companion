"""图片处理器

支持用户通过终端发送图片（文件路径），AI 能识别和回应图片内容。
使用 LLM 的 vision 能力（如果模型支持）。

终端使用方式：
- 用户输入 /img <图片路径> 来发送图片
- 或输入 /img 粘贴 base64 编码的图片
"""

import base64
import mimetypes
from pathlib import Path

from loguru import logger


class ImageHandler:
    """图片处理器

    功能：
    1. 读取本地图片文件，转换为 base64
    2. 构建包含图片的消息格式（兼容 OpenAI vision API）
    3. 生成图片描述的 prompt

    使用方式：
    - 用户在终端输入 /img <文件路径>
    - handler 读取图片并构建 vision 消息
    - 传递给 LLM 进行视觉理解
    """

    VISION_PROMPT = """你的女朋友给你发了一张图片。请用你的人设身份，自然地描述你看到的内容并回应。

要求：
1. 像真人一样描述图片内容（不要说"这张图片显示了..."，而是自然地说）
2. 结合图片内容表达你的情感和想法
3. 回复控制在 1-3 句话
4. 可以问问题来延续对话"""

    # 支持的图片格式
    SUPPORTED_FORMATS = {
        '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp',
    }

    def __init__(self):
        pass

    def load_image(self, path: str) -> tuple[str, str] | None:
        """读取本地图片并转为 base64

        Args:
            path: 图片文件路径

        Returns:
            (base64_data, mime_type) 元组，失败返回 None
        """
        filepath = Path(path.strip().strip('"').strip("'"))

        if not filepath.exists():
            logger.warning(f"Image file not found: {filepath}")
            return None

        if filepath.suffix.lower() not in self.SUPPORTED_FORMATS:
            logger.warning(f"Unsupported image format: {filepath.suffix}")
            return None

        try:
            # 检查文件大小（限制 10MB）
            file_size = filepath.stat().st_size
            if file_size > 10 * 1024 * 1024:
                logger.warning(f"Image too large: {file_size / 1024 / 1024:.1f}MB")
                return None

            with open(filepath, "rb") as f:
                data = f.read()

            b64_data = base64.b64encode(data).decode("utf-8")
            mime_type = mimetypes.guess_type(str(filepath))[0] or "image/jpeg"

            logger.info(f"Loaded image: {filepath.name} ({file_size / 1024:.1f}KB)")
            return b64_data, mime_type

        except Exception as e:
            logger.error(f"Failed to load image: {e}")
            return None

    def build_vision_messages(
        self, b64_data: str, mime_type: str, user_text: str = ""
    ) -> list[dict]:
        """构建包含图片的消息列表（兼容 OpenAI vision API）

        Args:
            b64_data: base64 编码的图片数据
            mime_type: 图片 MIME 类型
            user_text: 用户附带的文字说明

        Returns:
            消息列表
        """
        image_content = {
            "type": "image_url",
            "image_url": {
                "url": f"data:{mime_type};base64,{b64_data}",
            },
        }

        text_content = {
            "type": "text",
            "text": user_text if user_text else "（发了一张图片）",
        }

        return [
            {
                "role": "user",
                "content": [text_content, image_content],
            }
        ]

    def get_vision_prompt(self) -> str:
        """获取图片理解的 system prompt"""
        return self.VISION_PROMPT

    @staticmethod
    def parse_img_command(user_input: str) -> tuple[str, str]:
        """解析 /img 命令

        Args:
            user_input: 用户输入，格式如 /img path/to/image.jpg 你好看看这个

        Returns:
            (image_path, user_text) 元组
        """
        # 去掉 /img 前缀
        content = user_input[4:].strip()

        if not content:
            return "", ""

        # 尝试分离文件路径和文字说明
        # 支持带引号的路径：/img "path with spaces.jpg" 看看这个
        if content.startswith('"'):
            try:
                end_quote = content.index('"', 1)
                image_path = content[1:end_quote]
                user_text = content[end_quote + 1:].strip()
            except ValueError:
                return "", ""
        elif content.startswith("'"):
            try:
                end_quote = content.index("'", 1)
                image_path = content[1:end_quote]
                user_text = content[end_quote + 1:].strip()
            except ValueError:
                return "", ""
        else:
            # 按空格分割，第一部分是路径
            parts = content.split(maxsplit=1)
            image_path = parts[0]
            user_text = parts[1] if len(parts) > 1 else ""

        return image_path, user_text