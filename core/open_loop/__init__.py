"""Open Loop Engine — 事件追踪引擎

将用户提到的未来事件自动创建为可追踪事件。
支持：自动创建、自动追问、状态变更、超时失效。

事件状态：pending → resolved / failed / abandoned
"""

from .engine import OpenLoop, OpenLoopEngine, OpenLoopStorage

__all__ = [
    "OpenLoop",
    "OpenLoopEngine",
    "OpenLoopStorage",
]
