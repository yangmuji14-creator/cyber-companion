"""Personality Engine — 动态人格系统

提供：
- PersonalityState: 人格状态数据模型（信任、依赖、开放度、喜爱、嫉妒）
- PersonalityEngine: 人格成长引擎，根据交互动态更新人格状态
"""

from .models import PersonalityState
from .engine import PersonalityEngine

__all__ = ["PersonalityState", "PersonalityEngine"]
