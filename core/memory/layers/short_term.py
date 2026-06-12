"""Short Term Memory — 短期记忆（Layer 2）

保存：最近7天摘要
存储：JSON 文件
自动清理过期摘要
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from loguru import logger

from core.utils import atomic_write_json


@dataclass
class DailySummary:
    """每日摘要"""
    date: str           # YYYY-MM-DD
    summary: str        # 摘要内容
    message_count: int  # 当日消息数
    key_topics: list[str] = field(default_factory=list)  # 关键话题
    emotions: list[str] = field(default_factory=list)     # 主要情绪
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "summary": self.summary,
            "message_count": self.message_count,
            "key_topics": self.key_topics,
            "emotions": self.emotions,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DailySummary":
        return cls(
            date=data["date"],
            summary=data["summary"],
            message_count=data.get("message_count", 0),
            key_topics=data.get("key_topics", []),
            emotions=data.get("emotions", []),
            created_at=data.get("created_at", ""),
        )


class ShortTermMemory:
    """短期记忆：最近7天的每日摘要"""

    def __init__(self, data_dir: str | Path, retention_days: int = 7):
        self._data_dir = Path(data_dir) / "short_term"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._retention_days = retention_days
        self._summaries: dict[str, DailySummary] = {}
        self._load()

    def _load(self):
        """加载所有摘要"""
        for file in self._data_dir.glob("*.json"):
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                summary = DailySummary.from_dict(data)
                self._summaries[summary.date] = summary
            except Exception as e:
                logger.warning(f"Failed to load short-term memory {file}: {e}")

    def _save(self, date: str):
        """保存指定日期的摘要"""
        if date not in self._summaries:
            return
        file = self._data_dir / f"{date}.json"
        try:
            atomic_write_json(file, self._summaries[date].to_dict())
        except Exception as e:
            logger.error(f"Failed to save short-term memory: {e}")

    def add_summary(self, summary: DailySummary) -> None:
        """添加或更新每日摘要"""
        self._summaries[summary.date] = summary
        self._save(summary.date)
        self._cleanup_old()

    def get_today_summary(self) -> DailySummary | None:
        """获取今天的摘要"""
        today = datetime.now().strftime("%Y-%m-%d")
        return self._summaries.get(today)

    def get_recent_days(self, days: int = 7) -> list[DailySummary]:
        """获取最近 N 天的摘要"""
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        result = [
            s for s in self._summaries.values()
            if s.date >= cutoff
        ]
        result.sort(key=lambda s: s.date, reverse=True)
        return result

    def get_context_prompt(self, days: int = 3) -> str:
        """生成短期记忆上下文 prompt"""
        recent = self.get_recent_days(days)
        if not recent:
            return ""

        lines = ["【最近几天的对话摘要】"]
        for summary in recent:
            topics = "、".join(summary.key_topics[:3]) if summary.key_topics else "日常聊天"
            lines.append(f"- {summary.date}: {summary.summary[:100]}...（话题：{topics}）")

        return "\n".join(lines)

    def _cleanup_old(self):
        """清理过期摘要"""
        cutoff = (datetime.now() - timedelta(days=self._retention_days)).strftime("%Y-%m-%d")
        old_dates = [d for d in self._summaries if d < cutoff]
        for date in old_dates:
            del self._summaries[date]
            file = self._data_dir / f"{date}.json"
            if file.exists():
                file.unlink()
        if old_dates:
            logger.debug(f"Cleaned up {len(old_dates)} old daily summaries")

    def to_dict(self) -> dict[str, Any]:
        """序列化"""
        return {
            "retention_days": self._retention_days,
            "summaries": {d: s.to_dict() for d, s in self._summaries.items()},
        }

    @property
    def size(self) -> int:
        return len(self._summaries)
