"""大脑模块 — AI 自主内心独白生成系统 + 人设一致性检查

负责将情绪、人格、身份、人生总结等子系统状态
编织为连贯的内心独白，保持人设一致性。
"""

from .checker import CharacterBreakDetector, CharacterBreakResult
from .collector import StateCollector
from .coordinator import BrainCoordinator
from .models import BrainConfig, BrainDisabledError, BrainInput, BrainOutput, MonologueThought
from .organizer import ThoughtOrganizer
from .triggers import MemoryTrigger
from .weaver import MonologueWeaver


def create_brain(config: dict) -> BrainConfig | None:
    """检查配置并返回 BrainConfig 或 None（禁用时）

    Args:
        config: 来自 load_advanced() 的配置字典

    Returns:
        brain_enabled=True 时返回 BrainConfig，否则返回 None
    """
    if not config.get("brain_enabled", True):
        return None
    return BrainConfig(
        enabled=True,
        max_tokens=config.get("brain_max_tokens", 1000),
        debug=config.get("brain_debug", False),
        checker_enabled=config.get("checker_enabled", True),
    )


__all__ = [
    "BrainConfig",
    "BrainCoordinator",
    "BrainDisabledError",
    "BrainInput",
    "BrainOutput",
    "CharacterBreakDetector",
    "CharacterBreakResult",
    "MemoryTrigger",
    "MonologueThought",
    "MonologueWeaver",
    "StateCollector",
    "ThoughtOrganizer",
    "create_brain",
]
