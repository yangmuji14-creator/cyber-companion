"""人格引擎 — 动态人格成长系统

人格不再是静态 prompt，而是随时间、互动动态变化的系统。

五维人格模型：
- trust (信任): 对人的信任程度
- dependence (依赖): 情感依赖程度
- openness (开放度): 愿意分享的程度
- affection (亲密度): 情感亲密程度
- jealousy (嫉妒度): 容易吃醋的程度

每个人格维度 0.0~1.0，初始值由人设决定，后续根据互动动态变化。
"""

import json
import math
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from loguru import logger

from core.affection.constants import MAX_DIMENSION, MIN_DIMENSION
from core.affection.mapper import AffectionMapper


@dataclass
class PersonalityState:
    """人格状态 — 五维人格模型

    每个维度 0.0~1.0，随时间衰减，根据互动动态更新。
    """
    trust: float = 0.3        # 信任度
    dependence: float = 0.2   # 依赖度
    openness: float = 0.3     # 开放度
    affection: float = 0.2    # 亲密度
    jealousy: float = 0.3     # 嫉妒度

    # 元数据
    total_interactions: int = 0       # 总交互次数
    total_duration_minutes: int = 0    # 总交互时长（分钟）
    last_interaction: str = field(default_factory=lambda: datetime.now().isoformat())
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    # 情感分布统计
    positive_count: int = 0    # 积极情感次数
    negative_count: int = 0    # 消极情感次数
    neutral_count: int = 0     # 中性次数

    def to_dict(self) -> dict[str, Any]:
        return {
            "trust": round(self.trust, 3),
            "dependence": round(self.dependence, 3),
            "openness": round(self.openness, 3),
            "affection": round(self.affection, 3),
            "jealousy": round(self.jealousy, 3),
            "total_interactions": self.total_interactions,
            "total_duration_minutes": self.total_duration_minutes,
            "last_interaction": self.last_interaction,
            "created_at": self.created_at,
            "positive_count": self.positive_count,
            "negative_count": self.negative_count,
            "neutral_count": self.neutral_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PersonalityState":
        return cls(
            trust=data.get("trust", 0.3),
            dependence=data.get("dependence", 0.2),
            openness=data.get("openness", 0.3),
            affection=data.get("affection", 0.2),
            jealousy=data.get("jealousy", 0.3),
            total_interactions=data.get("total_interactions", 0),
            total_duration_minutes=data.get("total_duration_minutes", 0),
            last_interaction=data.get("last_interaction", datetime.now().isoformat()),
            created_at=data.get("created_at", datetime.now().isoformat()),
            positive_count=data.get("positive_count", 0),
            negative_count=data.get("negative_count", 0),
            neutral_count=data.get("neutral_count", 0),
        )


class PersonalityEngine:
    """人格引擎 — 管理人格状态的加载、更新和衰减

    更新规则：
    - 每次正面互动：trust +0.01, openness +0.005, affection +0.01
    - 每次负面互动：trust -0.02, dependence +0.01, jealousy +0.01
    - 每天不互动：所有维度 -0.005（回归初始）
    - 总互动次数增加：dependence +0.001/次
    """

    # 初始值模板
    BASE_PROFILES = {
        "热情": PersonalityState(trust=0.4, dependence=0.3, openness=0.5, affection=0.3, jealousy=0.2),
        "高冷": PersonalityState(trust=0.2, dependence=0.1, openness=0.2, affection=0.1, jealousy=0.4),
        "温柔": PersonalityState(trust=0.5, dependence=0.4, openness=0.4, affection=0.4, jealousy=0.3),
        "活泼": PersonalityState(trust=0.4, dependence=0.3, openness=0.6, affection=0.3, jealousy=0.3),
        "傲娇": PersonalityState(trust=0.2, dependence=0.4, openness=0.2, affection=0.3, jealousy=0.6),
    }

    def __init__(self, data_dir: str | Path):
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._data_dir / "personality.db"
        self._local = threading.local()
        self._cache: dict[str, PersonalityState] = {}
        self._lock = threading.Lock()
        self._init_db()

    @property
    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(str(self._db_path))
            conn.execute("PRAGMA journal_mode=WAL")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return self._local.conn

    def _init_db(self):
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS personalities (
                    user_id TEXT PRIMARY KEY,
                    state   TEXT NOT NULL
                )
            """)
            conn.commit()

    # ---- 公开接口 ----

    def get_state(self, user_id: str, profile: str | None = None) -> PersonalityState:
        """获取用户对应的人格状态

        Args:
            user_id: 用户 ID
            profile: 初始模板（首次加载时使用），如 "温柔"、"活泼"

        Returns:
            当前人格状态
        """
        if user_id in self._cache:
            state = self._cache[user_id]
        else:
            state = self._load(user_id)
            # 如果是新用户，使用模板初始化
            if state.total_interactions == 0 and profile:
                template = self.BASE_PROFILES.get(profile)
                if template:
                    state = PersonalityState(
                        trust=template.trust,
                        dependence=template.dependence,
                        openness=template.openness,
                        affection=template.affection,
                        jealousy=template.jealousy,
                    )
            self._cache[user_id] = state
        self._apply_decay(state)
        return state

    def update_from_llm(
        self,
        user_id: str,
        affection_impact: dict | None = None,
        personality_shift: dict | None = None,
        persona_id: str = "default",
    ) -> None:
        """Update personality based on LLM's enriched analysis.

        The LLM provides fine-grained affection_impact (direction, level, reason)
        and personality_shift (dimension → up/down/no_change), replacing the
        previous hardcoded emotion_type rules.

        Args:
            user_id: User identifier
            affection_impact: Dict with direction, level, reason from LLM
            personality_shift: Dict with dimension → "up"/"down"/"no_change"
            persona_id: Persona identifier (for future use with multi-persona)
        """
        with self._lock:
            state = self.get_state(user_id)

            # Apply personality shifts from LLM
            if personality_shift:
                shifts = AffectionMapper.map_personality_shift(personality_shift)
                for dimension, delta in shifts.items():
                    current = getattr(state, dimension, None)
                    if current is not None:
                        new_val = max(
                            MIN_DIMENSION,
                            min(MAX_DIMENSION, current + delta),
                        )
                        setattr(state, dimension, new_val)

            # Update interaction metadata
            state.total_interactions = getattr(state, "total_interactions", 0) + 1
            state.last_interaction = datetime.now().isoformat()

            self._save(user_id, state)

    def update_after_interaction(
        self,
        user_id: str,
        emotion_type: str,
        duration_minutes: int = 1,
        profile: str | None = None,
    ) -> PersonalityState:
        """[DEPRECATED] Use :meth:`update_from_llm` instead.

        For backward compatibility during transition period.
        Extracts basic affection direction from emotion_type and delegates
        to :meth:`update_from_llm`.

        .. note::
            ``duration_minutes`` and ``profile`` parameters are kept for
            backward compatibility but are no longer applied in the new
            LLM-driven pipeline. ``profile`` is still used for state
            initialization via :meth:`get_state`.
        """
        # Map emotion_type to basic affection_impact direction
        direction_map = {
            "happy": "slight_positive",
            "love": "positive",
            "excited": "positive",
            "sad": "slight_negative",
            "angry": "negative",
            "anxious": "slight_negative",
            "lonely": "neutral",
            "neutral": "neutral",
        }
        direction = direction_map.get(emotion_type, "neutral")
        affection_impact = {
            "direction": direction,
            "level": "low",
            "reason": "legacy_emotion_map",
        }

        # Default personality_shift from emotion type
        if emotion_type in ("happy", "love", "excited"):
            personality_shift = {"trust": "up", "dependence": "up"}
        elif emotion_type in ("sad", "angry"):
            personality_shift = {"trust": "down", "dependence": "up"}
        else:
            personality_shift = {}

        self.update_from_llm(user_id, affection_impact, personality_shift)
        return self.get_state(user_id, profile)

    def get_personality_context(self, user_id: str) -> str:
        """生成人格描述，用于 prompt 构建

        Returns:
            人格描述文本
        """
        state = self.get_state(user_id)

        def _desc(value: float, high_label: str, mid_label: str, low_label: str) -> str:
            if value >= 0.7:
                return high_label
            elif value >= 0.4:
                return mid_label
            else:
                return low_label

        trust_desc = _desc(state.trust, "很信任你", "比较信任你", "还在观察你")
        dep_desc = _desc(state.dependence, "很依赖你", "有点依赖你", "比较独立")
        open_desc = _desc(state.openness, "什么话都愿意说", "愿意分享日常", "话不多")
        aff_desc = _desc(state.affection, "很喜欢你", "对你有好感", "还在熟悉")
        jeal_desc = _desc(state.jealousy, "容易吃醋", "偶尔会吃醋", "不太吃醋")

        return (
            "【当前人格状态】\n"
            f"信任：{trust_desc}\n"
            f"依赖：{dep_desc}\n"
            f"开放：{open_desc}\n"
            f"好感：{aff_desc}\n"
            f"醋意：{jeal_desc}"
        )

    def reset(self, user_id: str, profile: str | None = None) -> None:
        """重置人格状态"""
        with self._lock:
            if profile:
                template = self.BASE_PROFILES.get(profile)
                if template:
                    state = PersonalityState(
                        trust=template.trust, dependence=template.dependence,
                        openness=template.openness, affection=template.affection,
                        jealousy=template.jealousy,
                    )
                else:
                    state = PersonalityState()
            else:
                state = PersonalityState()
            self._cache[user_id] = state
            self._save(user_id, state)
            logger.info(f"Personality reset for user {user_id}")

    # ---- 内部 ----

    def _apply_decay(self, state: PersonalityState):
        """长时间不互动时，人格缓慢回归初始"""
        try:
            last = datetime.fromisoformat(state.last_interaction)
        except (ValueError, TypeError):
            return

        days = (datetime.now() - last).total_seconds() / 86400
        if days < 1:
            return  # 1 天内不衰减

        decay = min(days * 0.005, 0.1)  # 每天 0.5%，最多衰减 10%
        state.trust = max(0.1, state.trust - decay)
        state.dependence = max(0.1, state.dependence - decay * 1.5)
        state.openness = max(0.1, state.openness - decay)
        state.affection = max(0.1, state.affection - decay)

    def _load(self, user_id: str) -> PersonalityState:
        cur = self._conn.execute(
            "SELECT state FROM personalities WHERE user_id=?", (user_id,)
        )
        row = cur.fetchone()
        if row:
            try:
                return PersonalityState.from_dict(json.loads(row["state"]))
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.warning(f"Failed to load personality for {user_id}: {e}")
        return PersonalityState()

    def _save(self, user_id: str, state: PersonalityState) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO personalities (user_id, state) VALUES (?, ?)",
            (user_id, json.dumps(state.to_dict(), ensure_ascii=False)),
        )
        self._conn.commit()

    def close(self):
        if hasattr(self._local, "conn") and self._local.conn:
            try:
                self._local.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except Exception:
                pass
            self._local.conn.close()
            self._local.conn = None
