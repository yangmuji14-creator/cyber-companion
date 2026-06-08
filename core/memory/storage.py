"""记忆存储层 - JSON 文件存储"""

import json
import os
import re
import tempfile
from pathlib import Path

from loguru import logger

from .models import Memory


class MemoryStorage:
    """JSON 文件存储层

    每个用户一个独立的 JSON 文件，存储在 data/memories/ 目录下。
    """

    def __init__(self, data_dir: str | Path):
        self._data_dir = Path(data_dir) / "memories"
        self._data_dir.mkdir(parents=True, exist_ok=True)

    def _get_user_file(self, user_id: str) -> Path:
        # 防止路径穿越：只允许字母数字下划线连字符
        safe_id = re.sub(r'[^a-zA-Z0-9_\-.]', '_', user_id)
        path = (self._data_dir / f"{safe_id}.json").resolve()
        if not path.is_relative_to(self._data_dir.resolve()):
            raise ValueError(f"Invalid user_id: {user_id}")
        return path

    def load(self, user_id: str) -> list[Memory]:
        """加载用户的所有记忆"""
        file_path = self._get_user_file(user_id)
        if not file_path.exists():
            return []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            memories = [Memory.from_dict(m) for m in data.get("memories", [])]
            logger.debug(f"Loaded {len(memories)} memories for user {user_id}")
            return memories
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to load memories for {user_id}: {e}")
            return []

    def save(self, user_id: str, memories: list[Memory]) -> None:
        """保存用户的所有记忆（原子写入）"""
        file_path = self._get_user_file(user_id)
        data = {"memories": [m.to_dict() for m in memories]}

        # 先写入临时文件，再原子替换，防止崩溃导致数据丢失
        tmp_fd, tmp_path = tempfile.mkstemp(dir=str(self._data_dir), suffix=".tmp")
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, str(file_path))
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

        logger.debug(f"Saved {len(memories)} memories for user {user_id}")

    def delete_all(self, user_id: str) -> bool:
        """删除用户所有记忆"""
        file_path = self._get_user_file(user_id)
        if file_path.exists():
            file_path.unlink()
            logger.info(f"Deleted all memories for user {user_id}")
            return True
        return False

    def list_users(self) -> list[str]:
        """列出所有有记忆的用户"""
        return [f.stem for f in self._data_dir.glob("*.json")]
