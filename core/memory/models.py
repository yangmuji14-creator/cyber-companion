"""记忆数据模型

支持结构化记忆分类和冲突检测。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class MemoryCategory(str, Enum):
    """记忆分类"""
    PERSONAL = "personal"       # 个人信息（名字、生日、年龄、地址等）
    EMOTION = "emotion"         # 情感相关（喜欢、讨厌、情绪表达）
    EVENT = "event"             # 事件（旅行、考试、纪念日等）
    PREFERENCE = "preference"   # 偏好（饮食、音乐、习惯等）
    RELATIONSHIP = "relationship"  # 关系（家人、朋友、社交关系）
    OPINION = "opinion"         # 观点/想法
    OTHER = "other"             # 其他


# 关键词 → 分类映射（用于快速分类）
CATEGORY_KEYWORDS: dict[MemoryCategory, list[str]] = {
    MemoryCategory.PERSONAL: [
        "名字", "叫", "生日", "年龄", "地址", "电话", "学校", "公司",
        "工作", "专业", "家乡", "住", "毕业", "学历",
    ],
    MemoryCategory.EMOTION: [
        "喜欢", "讨厌", "爱", "恨", "开心", "难过", "生气", "害怕",
        "梦想", "希望", "失望", "感动", "伤心", "愤怒",
    ],
    MemoryCategory.EVENT: [
        "旅行", "考试", "纪念日", "结婚", "毕业", "第一次", "比赛",
        "面试", "搬家", "入职", "离职", "生病", "手术",
    ],
    MemoryCategory.PREFERENCE: [
        "习惯", "最爱", "最讨厌", "经常", "总是", "口味", "偏好",
        "音乐", "电影", "美食", "运动", "游戏", "爱好",
    ],
    MemoryCategory.RELATIONSHIP: [
        "家人", "父母", "朋友", "同事", "男朋友", "女朋友",
        "老公", "老婆", "同学", "闺蜜", "兄弟",
    ],
    MemoryCategory.OPINION: [
        "觉得", "认为", "想法", "观点", "看法", "意见",
        "支持", "反对", "同意",
    ],
}


@dataclass
class Memory:
    """单条记忆

    支持结构化分类、标签、关系关联等。
    """

    id: str
    content: str
    level: int = 1  # 1-5 重要度
    category: str = "other"  # 记忆分类
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_accessed: str = field(default_factory=lambda: datetime.now().isoformat())
    access_count: int = 0
    tags: list[str] = field(default_factory=list)
    related_memory_ids: list[str] = field(default_factory=list)  # 关联记忆
    superseded_by: str = ""  # 被哪条记忆取代（冲突更新用）
    source: str = "auto"  # 来源：auto=自动提取, user=用户添加, summary=总结

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "content": self.content,
            "level": self.level,
            "category": self.category,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "access_count": self.access_count,
            "tags": self.tags,
        }
        # 只在有值时写入可选字段，节省空间
        if self.related_memory_ids:
            result["related_memory_ids"] = self.related_memory_ids
        if self.superseded_by:
            result["superseded_by"] = self.superseded_by
        if self.source != "auto":
            result["source"] = self.source
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Memory":
        return cls(
            id=data["id"],
            content=data["content"],
            level=data.get("level", 1),
            category=data.get("category", "other"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            last_accessed=data.get("last_accessed", datetime.now().isoformat()),
            access_count=data.get("access_count", 0),
            tags=data.get("tags", []),
            related_memory_ids=data.get("related_memory_ids", []),
            superseded_by=data.get("superseded_by", ""),
            source=data.get("source", "auto"),
        )

    def touch(self) -> None:
        """更新访问时间和次数"""
        self.last_accessed = datetime.now().isoformat()
        self.access_count += 1

    @property
    def is_superseded(self) -> bool:
        """是否已被取代"""
        return bool(self.superseded_by)

    @staticmethod
    def classify(content: str) -> str:
        """基于关键词快速分类记忆内容

        Args:
            content: 记忆内容

        Returns:
            分类字符串
        """
        scores: dict[MemoryCategory, int] = {}
        for category, keywords in CATEGORY_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in content)
            if score > 0:
                scores[category] = score

        if not scores:
            return MemoryCategory.OTHER.value

        return max(scores, key=scores.get).value  # type: ignore