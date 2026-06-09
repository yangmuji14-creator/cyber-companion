"""聊天历史持久化存储

将 _user_histories 和 _short_memories 从内存 dict 持久化到 JSON 文件。
"""

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from loguru import logger


class ChatHistoryStorage:
    """聊天历史持久化存储

    每个用户的数据包含：
    - messages: LLM 对话历史（role/content 列表，最多 max_messages 条）
    - short_memories: 短期记忆（user/assistant 对，用于总结）
    """

    def __init__(self, data_dir: str, max_messages: int = 20):
        """
        Args:
            data_dir: 数据存储目录
            max_messages: 每个用户保留的最大消息数
        """
        self._data_dir = Path(data_dir) / "chat_history"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._max_messages = max_messages
        # 内存缓存：user_id -> {"messages": [...], "short_memories": [...]}
        self._cache: dict[str, dict[str, list]] = {}

    def _get_user_file(self, user_id: str) -> Path:
        """获取用户历史文件路径（带路径穿越防护）"""
        safe_id = re.sub(r"[^a-zA-Z0-9_\-.]", "_", user_id)
        path = (self._data_dir / f"{safe_id}.json").resolve()
        if not path.is_relative_to(self._data_dir.resolve()):
            raise ValueError(f"Invalid user_id: {user_id}")
        return path

    def load(self, user_id: str) -> dict[str, list]:
        """加载用户聊天历史

        Returns:
            {"messages": [...], "short_memories": [...]}
        """
        if user_id in self._cache:
            return self._cache[user_id]

        filepath = self._get_user_file(user_id)
        if not filepath.exists():
            empty = {"messages": [], "short_memories": []}
            self._cache[user_id] = empty
            return empty

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            result = {
                "messages": data.get("messages", []),
                "short_memories": data.get("short_memories", []),
            }
            self._cache[user_id] = result
            return result
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load chat history for {user_id}: {e}")
            empty = {"messages": [], "short_memories": []}
            self._cache[user_id] = empty
            return empty

    def save(self, user_id: str) -> None:
        """保存用户聊天历史到文件（原子写入）"""
        if user_id not in self._cache:
            return

        filepath = self._get_user_file(user_id)
        data = self._cache[user_id]

        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=str(self._data_dir), suffix=".tmp"
            )
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, str(filepath))
        except Exception as e:
            logger.error(f"Failed to save chat history for {user_id}: {e}")

    def get_messages(self, user_id: str) -> list[dict[str, str]]:
        """获取用户 LLM 对话历史"""
        return self.load(user_id)["messages"]

    def add_message(self, user_id: str, role: str, content: str) -> None:
        """添加一条消息并持久化

        Args:
            user_id: 用户 ID
            role: 消息角色（user/assistant）
            content: 消息内容
        """
        data = self.load(user_id)
        data["messages"].append({"role": role, "content": content})

        # 裁剪到最大长度
        if len(data["messages"]) > self._max_messages:
            data["messages"] = data["messages"][-self._max_messages:]

        self.save(user_id)

    def get_short_memories(self, user_id: str) -> list[dict[str, str]]:
        """获取用户短期记忆"""
        return self.load(user_id)["short_memories"]

    def add_short_memory(self, user_id: str, user_msg: str, assistant_msg: str) -> None:
        """添加一组短期记忆并持久化"""
        data = self.load(user_id)
        data["short_memories"].append({"user": user_msg, "assistant": assistant_msg})
        self.save(user_id)

    def clear_short_memories(self, user_id: str) -> None:
        """清空用户短期记忆（总结后调用）"""
        data = self.load(user_id)
        data["short_memories"] = []
        self.save(user_id)

    def delete_user(self, user_id: str) -> bool:
        """删除用户所有聊天历史"""
        self._cache.pop(user_id, None)
        filepath = self._get_user_file(user_id)
        if filepath.exists():
            filepath.unlink()
            return True
        return False
