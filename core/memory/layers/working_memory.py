"""Working Memory — 工作记忆（Layer 1）

容量：20-50条消息
作用：当前对话的上下文窗口
存储：内存中，会话结束时可选持久化
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Message:
    """单条消息"""
    role: str          # "user" 或 "assistant"
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    emotion: str = ""
    importance: int = 3  # 1-5


class WorkingMemory:
    """工作记忆：当前对话的上下文窗口"""

    def __init__(self, max_messages: int = 30):
        self._max_messages = max_messages
        self._messages: list[Message] = []

    def add(self, message: Message) -> None:
        """添加一条消息"""
        self._messages.append(message)
        # 超出容量时移除最旧的
        if len(self._messages) > self._max_messages:
            self._messages = self._messages[-self._max_messages:]

    def get_recent(self, count: int = 10) -> list[Message]:
        """获取最近的 N 条消息"""
        return self._messages[-count:]

    def get_all(self) -> list[Message]:
        """获取所有消息"""
        return list(self._messages)

    def clear(self) -> None:
        """清空工作记忆"""
        self._messages.clear()

    def get_context_messages(self) -> list[dict[str, str]]:
        """获取用于 LLM 的上下文消息格式"""
        return [{"role": m.role, "content": m.content} for m in self._messages]

    def get_summary(self) -> str:
        """生成工作记忆摘要"""
        if not self._messages:
            return "暂无对话记录"

        total = len(self._messages)
        user_msgs = sum(1 for m in self._messages if m.role == "user")
        assistant_msgs = total - user_msgs

        # 最近的情绪分布
        emotions = [m.emotion for m in self._messages if m.emotion]
        emotion_dist = {}
        for e in emotions:
            emotion_dist[e] = emotion_dist.get(e, 0) + 1
        top_emotions = sorted(emotion_dist.items(), key=lambda x: x[1], reverse=True)[:3]

        lines = [f"共 {total} 条消息（用户 {user_msgs}，AI {assistant_msgs}）"]
        if top_emotions:
            emotion_str = "、".join(f"{e}({c})" for e, c in top_emotions)
            lines.append(f"情绪分布：{emotion_str}")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """序列化"""
        return {
            "max_messages": self._max_messages,
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    "timestamp": m.timestamp,
                    "emotion": m.emotion,
                    "importance": m.importance,
                }
                for m in self._messages
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkingMemory":
        """反序列化"""
        wm = cls(max_messages=data.get("max_messages", 30))
        for m_data in data.get("messages", []):
            wm.add(Message(
                role=m_data["role"],
                content=m_data["content"],
                timestamp=m_data.get("timestamp", ""),
                emotion=m_data.get("emotion", ""),
                importance=m_data.get("importance", 3),
            ))
        return wm

    @property
    def size(self) -> int:
        return len(self._messages)

    @property
    def is_full(self) -> bool:
        return len(self._messages) >= self._max_messages
