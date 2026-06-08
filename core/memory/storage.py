"""记忆存储层 - JSON 文件存储"""

import json
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
        return self._data_dir / f"{user_id}.json"

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
        """保存用户的所有记忆"""
        file_path = self._get_user_file(user_id)
        data = {"memories": [m.to_dict() for m in memories]}

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

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
