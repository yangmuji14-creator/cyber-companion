"""大脑模块数据模型

大脑模块是 AI 自主思考的核心子系统，负责：
- 将情绪/人格/身份/人生总结等系统状态编织为内心独白
- 在回复前产生一段「内心思考」以保持人设一致性
- 为 proactive 行为提供决策依据

本文件包含纯数据类，不包含业务逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MonologueThought:
    """单条内心思绪碎片

    由各个子系统（情绪/人格/身份/开放式循环等）产生，
    最终由 Brain 编织成一段连贯的内心独白。
    """

    source: str  # e.g. 'mood', 'openloop', 'identity', 'personality'
    content: str  # first-person thought text, e.g. "他一来我心情就亮了"
    priority: float = 0.5  # 0.0-1.0, higher = more important
    category: str = "feeling"  # 'feeling', 'memory', 'intention', 'observation', 'concern'


@dataclass
class BrainInput:
    """大脑模块的输入聚合容器

    收集来自情绪/人格/亲密度/身份/人生总结等所有子系统的状态，
    作为 Brain 编织内心独白的原材料。
    所有字段均为 Optional，允许部分子系统未就绪时正常工作。
    """

    # === 情绪系统 ===
    mood_valence: float | None = None
    mood_arousal: float | None = None
    mood_energy: float | None = None
    mood_type: str | None = None
    mood_intensity: float | None = None

    # === 对话/开放式循环 ===
    dialogue_thought: dict | None = None
    openloop_events: list[str] | None = None
    current_topic: str | None = None
    topic_keywords: list[str] | None = None
    chat_history_summary: str | None = None

    # === 人格系统 ===
    personality_trust: float | None = None
    personality_dependence: float | None = None
    personality_openness: float | None = None
    personality_affection: float | None = None
    personality_jealousy: float | None = None

    # === 亲密度系统 ===
    affection_level: float | None = None
    affection_days_known: int | None = None

    # === 身份/人生总结 ===
    identity_context: str | None = None
    life_summary: str | None = None

    # === 人设 ===
    persona_name: str | None = None
    persona_traits: list[str] | None = None
    drift_report: str | None = None

    # === 主动行为统计 ===
    proactive_times_today: int | None = None
    proactive_last_contact: str | None = None

    # === 时间环境 ===
    time_period: str | None = None  # 'morning', 'afternoon', 'evening', 'night', 'late_night'
    time_datetime: str | None = None  # ISO format

    # === 用户情绪 ===
    user_emotion: str | None = None
    user_emotion_intensity: float | None = None


@dataclass
class BrainOutput:
    """大脑模块的输出——最终生成的内心独白"""

    monologue: str  # the woven first-person narrative
    thoughts: list[MonologueThought] = field(default_factory=list)  # the individual thought fragments
    metadata: dict[str, Any] = field(default_factory=dict)  # debug info: token_count, sources_used, etc.


class BrainDisabledError(Exception):
    """Raised when brain is disabled via config."""
    pass


@dataclass
class BrainConfig:
    """大脑模块配置"""

    enabled: bool = True
    max_tokens: int = 1000
    debug: bool = False
    checker_enabled: bool = True
