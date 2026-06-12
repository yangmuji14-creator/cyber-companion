"""Life Summary Engine — 长期人生摘要引擎

定期生成用户的人生摘要：
    - 近期状态
    - 当前目标
    - 项目进展
    - 兴趣变化
    - 情绪趋势
    - 关系变化

规则：
    - 每 50~100 轮对话自动生成
    - 保存为结构化数据
    - 用于提高长期连续性

存储:
    data/life_summaries/{user_id}.json
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from core.utils import atomic_write_json


@dataclass
class LifeSummary:
    """人生摘要"""
    user_id: str
    summary: str = ""           # 自然语言摘要
    recent_status: str = ""     # 近期状态
    current_goals: list[str] = field(default_factory=list)
    project_progress: list[str] = field(default_factory=list)
    interest_changes: list[str] = field(default_factory=list)
    emotion_trend: str = ""     # 情绪趋势
    relationship_changes: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    message_count: int = 0      # 生成时的消息数

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "summary": self.summary,
            "recent_status": self.recent_status,
            "current_goals": self.current_goals,
            "project_progress": self.project_progress,
            "interest_changes": self.interest_changes,
            "emotion_trend": self.emotion_trend,
            "relationship_changes": self.relationship_changes,
            "created_at": self.created_at,
            "message_count": self.message_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LifeSummary":
        return cls(
            user_id=data.get("user_id", ""),
            summary=data.get("summary", ""),
            recent_status=data.get("recent_status", ""),
            current_goals=data.get("current_goals", []),
            project_progress=data.get("project_progress", []),
            interest_changes=data.get("interest_changes", []),
            emotion_trend=data.get("emotion_trend", ""),
            relationship_changes=data.get("relationship_changes", ""),
            created_at=data.get("created_at", datetime.now().isoformat()),
            message_count=data.get("message_count", 0),
        )

    def to_prompt(self) -> str:
        """生成摘要 prompt"""
        parts = ["【用户长期画像】"]
        if self.summary:
            parts.append(self.summary)
        if self.recent_status:
            parts.append(f"近期状态：{self.recent_status}")
        if self.current_goals:
            parts.append(f"当前目标：{', '.join(self.current_goals)}")
        if self.interest_changes:
            parts.append(f"兴趣变化：{', '.join(self.interest_changes)}")
        if self.emotion_trend:
            parts.append(f"情绪趋势：{self.emotion_trend}")
        return "\n".join(parts)


class LifeSummaryEngine:
    """人生摘要引擎"""

    def __init__(self, data_dir: str | Path):
        self._data_dir = Path(data_dir)
        self._path = self._data_dir / "life_summaries"
        self._path.mkdir(parents=True, exist_ok=True)

    def _file_path(self, user_id: str) -> Path:
        return self._path / f"{user_id}.json"

    def load(self, user_id: str) -> LifeSummary:
        """加载摘要"""
        path = self._file_path(user_id)
        if not path.exists():
            return LifeSummary(user_id=user_id)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return LifeSummary.from_dict(data)
        except Exception as e:
            logger.warning(f"Failed to load life summary for {user_id}: {e}")
            return LifeSummary(user_id=user_id)

    def save(self, summary: LifeSummary) -> None:
        """保存摘要"""
        path = self._file_path(summary.user_id)
        atomic_write_json(path, summary.to_dict())

    def generate(self, user_id: str, messages: list[dict], memories: list[Any]) -> LifeSummary:
        """基于聊天历史和记忆生成摘要

        简化规则：从记忆和聊天中提取关键信息。
        实际应由 LLM 生成，此处为降级实现。
        """
        summary = self.load(user_id)

        # 统计消息数
        msg_count = len(messages)
        if msg_count < 50:
            # 消息数太少，不生成
            return summary

        # 统计情绪
        emotions: dict[str, int] = {}
        for msg in messages:
            if isinstance(msg, dict) and "emotion" in msg:
                e = msg["emotion"]
                emotions[e] = emotions.get(e, 0) + 1

        if emotions:
            dominant = max(emotions, key=emotions.get)
            summary.emotion_trend = f"近期以{dominant}为主（{emotions[dominant]}次）"

        # 从记忆中提取目标和兴趣
        goals = []
        interests = []
        for mem in memories:
            if hasattr(mem, 'content'):
                content = mem.content
                if any(kw in content for kw in ["目标", "想", "计划", "打算"]):
                    goals.append(content)
                if any(kw in content for kw in ["喜欢", "爱好", "兴趣"]):
                    interests.append(content)

        summary.current_goals = goals[:5]
        summary.interest_changes = interests[:5]
        summary.message_count = msg_count
        summary.created_at = datetime.now().isoformat()

        # 生成一句话摘要
        parts = []
        if summary.emotion_trend:
            parts.append(summary.emotion_trend)
        if goals:
            parts.append(f"目标：{goals[0]}")
        if interests:
            parts.append(f"兴趣：{interests[0]}")
        summary.summary = "；".join(parts) if parts else ""

        self.save(summary)
        logger.info(f"LifeSummary generated for {user_id}: {summary.summary[:50]}...")
        return summary

    def get_context(self, user_id: str) -> str:
        """获取摘要上下文 prompt"""
        summary = self.load(user_id)
        if summary.message_count < 50:
            return ""
        return summary.to_prompt()

    def should_generate(self, user_id: str, current_msg_count: int) -> bool:
        """判断是否应该生成新摘要

        规则：每增加 50 条消息生成一次。
        """
        summary = self.load(user_id)
        return current_msg_count - summary.message_count >= 50
