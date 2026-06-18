"""大脑模块 — AI 自主内心独白生成系统

负责将情绪、人格、身份、人生总结等子系统状态
编织为连贯的内心独白，保持人设一致性。
"""

from .collector import StateCollector
from .models import BrainConfig, BrainInput, BrainOutput, MonologueThought
from .organizer import ThoughtOrganizer
from .weaver import MonologueWeaver

__all__ = [
    "BrainConfig",
    "BrainInput",
    "BrainOutput",
    "MonologueThought",
    "MonologueWeaver",
    "StateCollector",
    "ThoughtOrganizer",
]
