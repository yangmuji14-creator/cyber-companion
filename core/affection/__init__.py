"""亲密度系统 — 基础常量与数据模型"""

from .constants import (
    AffectionDirection,
    AffectionLevel,
    DIRECTION_LEVEL_MAP,
    PERSONALITY_SHIFT_MAP,
    BASE_BONUS,
    MIN_AFFECTION,
    MAX_AFFECTION,
    MIN_DIMENSION,
    MAX_DIMENSION,
)
from .schema import AffectionRecord, AffectionStats, AffectionStorage, CREATE_TABLE_SQL

__all__ = [
    "AffectionDirection",
    "AffectionLevel",
    "DIRECTION_LEVEL_MAP",
    "PERSONALITY_SHIFT_MAP",
    "BASE_BONUS",
    "MIN_AFFECTION",
    "MAX_AFFECTION",
    "MIN_DIMENSION",
    "MAX_DIMENSION",
    "AffectionRecord",
    "AffectionStats",
    "AffectionStorage",
    "CREATE_TABLE_SQL",
]
