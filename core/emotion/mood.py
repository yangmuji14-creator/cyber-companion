"""情绪状态机 — 跨 session 持续性情绪系统

情绪不再只是单轮检测结果，而是持续存在的状态：
- 检测到的情绪会改变 MoodState
- 情绪随时间逐渐衰减回归中性
- 跨 session 保持（SQLite 持久化）
- 影响回复风格和 prompt 构建

Mood 在 2D 空间上分布：效价（Valence）- 唤醒度（Arousal）
"""

import json
import math
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from loguru import logger

from .analyzer import EmotionType, EmotionResult


class MoodType(str, Enum):
    """情绪状态类型（基于效价-唤醒度 2D 模型）"""
    ECSTATIC = "ecstatic"       # 欣喜若狂 (高+ 高)
    HAPPY = "happy"             # 开心 (高+ 中)
    CONTENT = "content"         # 满足 (中+ 低)
    CALM = "calm"               # 平静 (中 低)
    NEUTRAL = "neutral"         # 中性 (0 0)
    TIRED = "tired"             # 疲惫 (低 低)
    SAD = "sad"                 # 难过 (低- 低)
    DEPRESSED = "depressed"     # 低落 (低- 中)
    LONELY = "lonely"           # 孤独 (低- 中)
    ANXIOUS = "anxious"         # 焦虑 (低- 高)
    ANGRY = "angry"             # 生气 (低- 高)
    FRUSTRATED = "frustrated"   # 烦躁 (低- 高)
    EXCITED = "excited"         # 兴奋 (高+ 高)
    LOVE = "love"               # 爱意 (高+ 中)
    GRATEFUL = "grateful"       # 感激 (高+ 低)


# MoodType → 2D 坐标 (valence, arousal)  valence: -1~1, arousal: 0~1
MOOD_COORDS: dict[MoodType, tuple[float, float]] = {
    MoodType.ECSTATIC:    (1.0, 1.0),
    MoodType.HAPPY:       (0.8, 0.6),
    MoodType.CONTENT:     (0.5, 0.2),
    MoodType.CALM:        (0.3, 0.1),
    MoodType.NEUTRAL:     (0.0, 0.0),
    MoodType.TIRED:       (-0.2, 0.1),
    MoodType.SAD:         (-0.6, 0.2),
    MoodType.DEPRESSED:   (-0.7, 0.4),
    MoodType.LONELY:      (-0.5, 0.3),
    MoodType.ANXIOUS:     (-0.4, 0.8),
    MoodType.ANGRY:       (-0.8, 0.9),
    MoodType.FRUSTRATED:  (-0.5, 0.7),
    MoodType.EXCITED:     (0.9, 0.9),
    MoodType.LOVE:        (0.9, 0.5),
    MoodType.GRATEFUL:    (0.7, 0.2),
}

# EmotionType → MoodType 映射（检测到的情绪如何影响 mood）
EMOTION_TO_MOOD: dict[EmotionType, MoodType] = {
    EmotionType.HAPPY:   MoodType.HAPPY,
    EmotionType.SAD:     MoodType.SAD,
    EmotionType.ANGRY:   MoodType.ANGRY,
    EmotionType.NEUTRAL: MoodType.NEUTRAL,
    EmotionType.EXCITED: MoodType.EXCITED,
    EmotionType.LONELY:  MoodType.LONELY,
    EmotionType.ANXIOUS: MoodType.ANXIOUS,
    EmotionType.LOVE:    MoodType.LOVE,
}

# Mood → emoji 映射
MOOD_EMOJI_MAP: dict[MoodType, str] = {
    MoodType.ECSTATIC: "🤩",
    MoodType.HAPPY: "😊",
    MoodType.CONTENT: "😌",
    MoodType.CALM: "🧘",
    MoodType.NEUTRAL: "😐",
    MoodType.TIRED: "😮‍💨",
    MoodType.SAD: "😢",
    MoodType.DEPRESSED: "😞",
    MoodType.LONELY: "🥺",
    MoodType.ANXIOUS: "😰",
    MoodType.ANGRY: "😤",
    MoodType.FRUSTRATED: "😩",
    MoodType.EXCITED: "🤩",
    MoodType.LOVE: "💖",
    MoodType.GRATEFUL: "🥹",
}

# Mood → 行为描述（用于 prompt）
MOOD_BEHAVIOR: dict[MoodType, str] = {
    MoodType.ECSTATIC:   "非常开心，充满活力，回复热情洋溢",
    MoodType.HAPPY:      "心情很好，回复温暖活泼",
    MoodType.CONTENT:    "心情平静满足，回复温和",
    MoodType.CALM:       "很平静，回复从容淡定",
    MoodType.NEUTRAL:    "情绪平稳，正常聊天",
    MoodType.TIRED:      "有点疲惫，回复简短慵懒",
    MoodType.SAD:        "有些难过，回复带着淡淡的忧伤",
    MoodType.DEPRESSED:  "情绪低落，不想多说，回复简短",
    MoodType.LONELY:     "有点孤独，渴望陪伴，回复带着思念",
    MoodType.ANXIOUS:    "有些焦虑不安，回复略显急促",
    MoodType.ANGRY:      "心情不好，有点烦躁，回复简短冷淡",
    MoodType.FRUSTRATED: "有点烦躁，耐性不太好",
    MoodType.EXCITED:    "很兴奋，回复充满热情",
    MoodType.LOVE:       "充满爱意，回复温柔甜蜜",
    MoodType.GRATEFUL:   "很感激，回复温暖真诚",
}


# 每种 Mood 的默认持续时间（小时），到期后自动回归中性
MOOD_DURATION_HOURS: dict[MoodType, float] = {
    MoodType.ECSTATIC: 1.0,      # 欣喜若狂 → 1 小时
    MoodType.HAPPY: 2.0,         # 开心 → 2 小时
    MoodType.CONTENT: 3.0,       # 满足 → 3 小时
    MoodType.CALM: 4.0,          # 平静 → 4 小时
    MoodType.NEUTRAL: 0.0,       # 中性 → 永久
    MoodType.TIRED: 4.0,         # 疲惫 → 4 小时
    MoodType.SAD: 6.0,           # 难过 → 6 小时
    MoodType.DEPRESSED: 8.0,     # 低落 → 8 小时
    MoodType.LONELY: 12.0,       # 孤独 → 12 小时
    MoodType.ANXIOUS: 3.0,       # 焦虑 → 3 小时
    MoodType.ANGRY: 2.0,         # 生气 → 2 小时
    MoodType.FRUSTRATED: 2.0,    # 烦躁 → 2 小时
    MoodType.EXCITED: 1.5,       # 兴奋 → 1.5 小时
    MoodType.LOVE: 4.0,          # 爱意 → 4 小时
    MoodType.GRATEFUL: 3.0,      # 感激 → 3 小时
}


@dataclass
class MoodState:
    """当前情绪状态"""
    mood: MoodType = MoodType.NEUTRAL
    valence: float = 0.0      # -1.0 ~ 1.0
    arousal: float = 0.0      # 0.0 ~ 1.0
    intensity: float = 0.0    # 0.0 ~ 1.0 当前 mood 强度
    energy: float = 0.5       # 0.0 ~ 1.0 精力水平
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_decay_at: str = field(default_factory=lambda: datetime.now().isoformat())
    expires_at: str | None = None  # mood 到期时间，到期后回归中性

    def to_dict(self) -> dict[str, Any]:
        result = {
            "mood": self.mood.value,
            "valence": round(self.valence, 3),
            "arousal": round(self.arousal, 3),
            "intensity": round(self.intensity, 3),
            "energy": round(self.energy, 3),
            "updated_at": self.updated_at,
            "last_decay_at": self.last_decay_at,
        }
        if self.expires_at:
            result["expires_at"] = self.expires_at
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MoodState":
        return cls(
            mood=MoodType(data.get("mood", "neutral")),
            valence=data.get("valence", 0.0),
            arousal=data.get("arousal", 0.0),
            intensity=data.get("intensity", 0.0),
            energy=data.get("energy", 0.5),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            last_decay_at=data.get("last_decay_at", datetime.now().isoformat()),
            expires_at=data.get("expires_at"),
        )

    def is_expired(self) -> bool:
        """判断情绪是否已到期"""
        if not self.expires_at:
            return False
        try:
            return datetime.now() > datetime.fromisoformat(self.expires_at)
        except (ValueError, TypeError):
            return False


class MoodEngine:
    """情绪状态机引擎

    职责：
    1. 加载/保存用户情绪状态
    2. 根据检测到的情绪更新状态
    3. 管理情绪衰减（随时间回归中性）
    4. 根据时间调节精力水平
    5. 提供 mood context 用于 prompt
    """

    def __init__(self, data_dir: str | Path):
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._data_dir / "moods.db"
        self._local = threading.local()
        self._cache: dict[str, MoodState] = {}
        self._init_db()

    @property
    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            from core.storage.db import open_db
            self._local.conn = open_db(self._db_path)
        return self._local.conn

    def _init_db(self):
        from core.storage.db import open_db
        with open_db(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS moods (
                    user_id TEXT PRIMARY KEY,
                    state   TEXT NOT NULL
                )
            """)

    # ---- 公开接口 ----

    def get_mood(self, user_id: str) -> MoodState:
        """获取用户当前情绪状态（含衰减计算）"""
        if user_id in self._cache:
            state = self._cache[user_id]
        else:
            state = self._load(user_id)
            self._cache[user_id] = state
        # 每次获取时应用衰减
        self._apply_decay(state)
        return state

    def update_from_emotion(self, user_id: str, emotion: EmotionResult) -> MoodState:
        """根据检测到的情绪更新 mood 状态"""
        mood = self.get_mood(user_id)

        # 检查是否过期
        if mood.is_expired():
            self.reset(user_id)
            mood = self.get_mood(user_id)

        detected_mood = EMOTION_TO_MOOD.get(emotion.emotion, MoodType.NEUTRAL)
        target_coords = MOOD_COORDS[detected_mood]

        # 情绪影响强度由检测强度决定
        influence = emotion.intensity * 0.4  # 每次对话的影响权重

        # 向检测到的情绪方向移动
        mood.valence += (target_coords[0] - mood.valence) * influence
        mood.arousal += (target_coords[1] - mood.arousal) * influence

        # 更新精力：积极情绪提升精力，消极情绪消耗精力
        if target_coords[0] > 0:
            mood.energy = min(1.0, mood.energy + influence * 0.3)
        elif target_coords[0] < 0:
            mood.energy = max(0.0, mood.energy - influence * 0.2)

        # 钳制
        mood.valence = max(-1.0, min(1.0, mood.valence))
        mood.arousal = max(0.0, min(1.0, mood.arousal))

        # 计算最近 mood 类型和强度
        nearest_mood, dist = self._find_nearest_mood(mood.valence, mood.arousal)
        mood.mood = nearest_mood
        mood.intensity = 1.0 - min(dist / 2.0, 1.0)
        mood.updated_at = datetime.now().isoformat()

        # 设置过期时间
        self._set_expires_at(mood)

        self._save(user_id, mood)
        logger.debug(
            f"Mood updated: {mood.mood.value} "
            f"(v={mood.valence:.2f}, a={mood.arousal:.2f}, "
            f"e={mood.energy:.2f}, i={mood.intensity:.2f}, "
            f"expires={mood.expires_at})"
        )
        return mood

    @staticmethod
    def _set_expires_at(state: MoodState):
        """根据 mood 类型设置过期时间"""
        if state.mood == MoodType.NEUTRAL:
            state.expires_at = None
            return
        duration = MOOD_DURATION_HOURS.get(state.mood, 2.0)
        if duration <= 0:
            state.expires_at = None
        else:
            expires = datetime.now() + timedelta(hours=duration * (0.5 + state.intensity * 0.5))
            state.expires_at = expires.isoformat()

    def get_mood_context(self, user_id: str) -> str:
        """生成情绪上下文，供 prompt 使用

        Returns:
            情绪描述文本，如「你现在心情很好，回复温暖活泼」
        """
        mood = self.get_mood(user_id)
        behavior = MOOD_BEHAVIOR.get(mood.mood, MOOD_BEHAVIOR[MoodType.NEUTRAL])

        # 强度修饰
        if mood.intensity < 0.2:
            prefix = "稍微"
        elif mood.intensity < 0.5:
            prefix = ""
        elif mood.intensity < 0.8:
            prefix = "比较"
        else:
            prefix = "非常"

        return f"你现在的情绪状态：{prefix}{mood.mood.value}（{behavior}）"

    def get_mood_emoji(self, user_id: str) -> str:
        """获取当前情绪对应的 emoji"""
        mood = self.get_mood(user_id)
        return MOOD_EMOJI_MAP.get(mood.mood, "😐")

    def decay_mood(self, user_id: str) -> None:
        """强制进行一次衰减（可在空闲循环调用）"""
        mood = self.get_mood(user_id)
        self._apply_decay(mood, force=True)
        self._save(user_id, mood)

    def reset(self, user_id: str) -> None:
        """重置用户情绪到中性"""
        state = MoodState()
        self._cache[user_id] = state
        self._save(user_id, state)
        logger.info(f"Mood reset for user {user_id}")

    # ---- 内部 ----

    def _apply_decay(self, state: MoodState, force: bool = False):
        """应用情绪衰减 — 情绪随时间回归中性

        每小时 valence 向 0 移动 0.02，arousal 向 0 移动 0.015
        """
        now = datetime.now()
        try:
            last = datetime.fromisoformat(state.last_decay_at)
        except (ValueError, TypeError):
            last = now

        hours = (now - last).total_seconds() / 3600
        if hours < 0.5 and not force:
            return  # 半小时内不衰减

        # 衰减量 = 时间 × 衰减率
        decay_factor = min(hours * 0.02, 0.5)  # 最多衰减 50%

        # 向中性回归
        state.valence += (0.0 - state.valence) * decay_factor
        state.arousal += (0.0 - state.arousal) * decay_factor
        state.energy += (0.5 - state.energy) * decay_factor * 0.5

        # 根据时间调整精力（早起精力好，晚上精力差）
        hour = now.hour
        if 6 <= hour < 12:
            target_energy = 0.7
        elif 12 <= hour < 18:
            target_energy = 0.6
        elif 18 <= hour < 22:
            target_energy = 0.5
        else:
            target_energy = 0.3  # 深夜
        state.energy += (target_energy - state.energy) * 0.3

        # 钳制
        state.valence = max(-1.0, min(1.0, state.valence))
        state.arousal = max(0.0, min(1.0, state.arousal))
        state.energy = max(0.0, min(1.0, state.energy))

        # 更新 mood 类型
        if abs(state.valence) < 0.05 and state.arousal < 0.05:
            state.mood = MoodType.NEUTRAL
            state.intensity = 0.0
        else:
            nearest, dist = self._find_nearest_mood(state.valence, state.arousal)
            state.mood = nearest
            state.intensity = 1.0 - min(dist / 2.0, 1.0)

        state.last_decay_at = now.isoformat()

    @staticmethod
    def _find_nearest_mood(valence: float, arousal: float) -> tuple[MoodType, float]:
        """在 mood 坐标空间中找到最近的 MoodType"""
        nearest = MoodType.NEUTRAL
        min_dist = float("inf")
        for mood, (mv, ma) in MOOD_COORDS.items():
            dist = math.sqrt((valence - mv) ** 2 + (arousal - ma) ** 2)
            if dist < min_dist:
                min_dist = dist
                nearest = mood
        return nearest, min_dist

    def _load(self, user_id: str) -> MoodState:
        """从 SQLite 加载情绪状态"""
        cur = self._conn.execute(
            "SELECT state FROM moods WHERE user_id=?", (user_id,)
        )
        row = cur.fetchone()
        if row:
            try:
                return MoodState.from_dict(json.loads(row["state"]))
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.warning(f"Failed to load mood for {user_id}: {e}")
        return MoodState()

    def _save(self, user_id: str, state: MoodState) -> None:
        """保存情绪状态到 SQLite"""
        self._conn.execute(
            "INSERT OR REPLACE INTO moods (user_id, state) VALUES (?, ?)",
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
