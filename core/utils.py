"""通用工具函数

提取跨模块复用的模式：LLM JSON 响应解析、原子文件写入。
"""

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from loguru import logger

# LLM 响应中 markdown 代码块的正则
_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*\n(.*?)\n```", re.DOTALL)


def parse_json_response(text: str) -> dict[str, Any] | None:
    """从 LLM 响应文本中提取并解析 JSON

    支持：
    - 纯 JSON 字符串
    - markdown 代码块包裹的 JSON（```json ... ```）

    Args:
        text: LLM 原始响应文本

    Returns:
        解析后的 dict，失败返回 None
    """
    text = text.strip()
    if not text:
        return None

    # 尝试从 markdown 代码块中提取
    match = _JSON_BLOCK_RE.search(text)
    if match:
        text = match.group(1).strip()

    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    return None


def atomic_write_json(path: str | Path, data: Any, *, indent: int = 2) -> None:
    """原子写入 JSON 文件

    先写入临时文件，再原子替换，防止崩溃导致数据丢失。
    临时文件与目标文件在同一目录下（保证 os.replace 原子性）。

    Args:
        path: 目标文件路径
        data: 要序列化的数据
        indent: JSON 缩进（默认 2）
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)
        os.replace(tmp_path, str(path))
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def read_json(path: str | Path, *, default: Any = None) -> Any:
    """安全读取 JSON 文件

    Args:
        path: 文件路径
        default: 文件不存在或解析失败时的默认值

    Returns:
        解析后的数据，或 default
    """
    path = Path(path)
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to read JSON {path}: {e}")
        return default
