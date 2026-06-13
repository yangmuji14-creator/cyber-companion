"""Multi-Layer Memory System — 四层记忆架构

Layer 1: Working Memory — 工作记忆（20-50条消息，上下文窗口）
Layer 2: Short Term Memory — 短期记忆（最近7天摘要）
Layer 3: Long Term Memory — 长期记忆（重要事实）
Layer 4: Life Summary — 生活总结（AI自动生成用户画像）
"""

from .working_memory import WorkingMemory
from .short_term import ShortTermMemory
from .long_term import LongTermMemory
from .life_summary import LifeSummary
from .manager import MultiLayerMemoryManager

__all__ = [
    "WorkingMemory",
    "ShortTermMemory",
    "LongTermMemory",
    "LifeSummary",
    "MultiLayerMemoryManager",
]
