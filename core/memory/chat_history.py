"""聊天历史持久化存储

将 _user_histories 和 _short_memories 从内存 dict 持久化到 JSON 文件。
"""

import json
import os
import re
import tempfile
from datetime import datetime
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

    def add_message(
        self,
        user_id: str,
        role: str,
        content: str,
        emotion: str | None = None,
        emotion_intensity: float | None = None,
    ) -> None:
        """添加一条消息并持久化

        Args:
            user_id: 用户 ID
            role: 消息角色（user/assistant）
            content: 消息内容
            emotion: 情感类型（可选，如 "happy", "sad" 等）
            emotion_intensity: 情感强度 0.0-1.0（可选）
        """
        data = self.load(user_id)
        msg: dict[str, Any] = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        }
        if emotion is not None:
            msg["emotion"] = emotion
        if emotion_intensity is not None:
            msg["emotion_intensity"] = round(emotion_intensity, 3)
        data["messages"].append(msg)

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

    def delete_last_messages(self, user_id: str, count: int = 2) -> list[dict[str, Any]]:
        """删除最后 N 条消息，返回被删除的消息列表

        Args:
            user_id: 用户 ID
            count: 要删除的消息数量

        Returns:
            被删除的消息列表（从旧到新）
        """
        data = self.load(user_id)
        messages = data["messages"]
        if not messages:
            return []

        count = min(count, len(messages))
        deleted = messages[-count:]
        data["messages"] = messages[:-count]
        self.save(user_id)
        return deleted

    def search_messages(
        self, user_id: str, keyword: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """搜索包含关键词的消息

        Args:
            user_id: 用户 ID
            keyword: 搜索关键词
            limit: 最大返回数量

        Returns:
            匹配结果列表，每项包含 index, message, before, after
        """
        messages = self.get_messages(user_id)
        if not messages or not keyword:
            return []

        keyword_lower = keyword.lower()
        results = []
        for i, msg in enumerate(messages):
            content = msg.get("content", "")
            if keyword_lower in content.lower():
                before = messages[i - 1] if i > 0 else None
                after = messages[i + 1] if i < len(messages) - 1 else None
                results.append({
                    "index": i,
                    "message": msg,
                    "before": before,
                    "after": after,
                })
                if len(results) >= limit:
                    break
        return results

    def delete_user(self, user_id: str) -> bool:
        """删除用户所有聊天历史"""
        self._cache.pop(user_id, None)
        filepath = self._get_user_file(user_id)
        if filepath.exists():
            filepath.unlink()
            return True
        return False

    def export_markdown(self, user_id: str, persona_name: str = "AI") -> str:
        """将聊天历史导出为 Markdown 格式

        Args:
            user_id: 用户 ID
            persona_name: AI 角色名

        Returns:
            Markdown 格式的聊天记录字符串
        """
        messages = self.get_messages(user_id)
        if not messages:
            return ""

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [
            f"# 💬 聊天记录",
            f"",
            f"> 导出时间：{now}",
            f"> 角色：{persona_name}",
            f"> 消息数：{len(messages)}",
            f"",
            f"---",
            f"",
        ]

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            ts = msg.get("timestamp", "")
            time_str = ""
            if ts:
                try:
                    dt = datetime.fromisoformat(ts)
                    time_str = f" `{dt.strftime('%H:%M')}`"
                except (ValueError, TypeError):
                    pass

            if role == "user":
                label = "🧑 你"
            elif role == "assistant":
                label = f"💕 {persona_name}"
            else:
                label = role

            lines.append(f"**{label}**{time_str}")
            lines.append(f"")
            lines.append(f"{content}")
            lines.append(f"")
            lines.append(f"---")
            lines.append(f"")

        return "\n".join(lines)
