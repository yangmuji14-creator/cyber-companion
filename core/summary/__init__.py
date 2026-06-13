"""人生摘要引擎 — 每 N 轮自动生成用户人生摘要

提高长期连续性，避免仅依赖零散记忆。
"""

from .engine import LifeSummary, LifeSummaryEngine

__all__ = [
    "LifeSummary",
    "LifeSummaryEngine",
]
