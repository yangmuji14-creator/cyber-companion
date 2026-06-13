"""AI Mood — 让 AI 每天有不同的心情和状态

核心逻辑：
  - 每个 persona 每天计算一次 mood（情绪 + 精力 + 主题）
  - 情绪受关系亲密度影响（亲密度高更容易开心）
  - 注入到 system prompt，影响回复风格
  - 持久化到 data/ai_mood.json，跨 session 不丢失
"""

import json
import random
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from loguru import logger

from core.utils import atomic_write_json


# ========== 情绪映射表 ==========

MOOD_POOL = [
    "happy", "calm", "excited", "tired",
    "melancholy", "playful", "affectionate", "quiet",
]

MOOD_STYLE: dict[str, str] = {
    "happy": "你今天心情很好，说话活泼开朗，语言充满元气",
    "calm": "你今天很平静安详，说话温柔平和",
    "excited": "你今天很兴奋，对话题充满热情和好奇心",
    "tired": "你今天有点疲惫，说话懒洋洋的，简短而柔软",
    "melancholy": "你今天有点忧郁感伤，说话带着淡淡的情绪",
    "playful": "你今天很想逗对方玩，说话俏皮爱开玩笑",
    "affectionate": "你今天特别想亲近对方，说话温柔体贴带点撒娇",
    "quiet": "你今天比较安静内向，话不多但每一句都很用心",
}


# ========== 数据模型 ==========

@dataclass
class AIMoodState:
    persona_id: str
    emotion: str = "calm"
    energy: int = 70
    today_theme: str = ""
    last_updated: date = date(2020, 1, 1)

    def to_dict(self) -> dict:
        return {
            "persona_id": self.persona_id,
            "emotion": self.emotion,
            "energy": self.energy,
            "today_theme": self.today_theme,
            "last_updated": self.last_updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AIMoodState":
        raw = d.get("last_updated", "")
        if isinstance(raw, str):
            try:
                last = date.fromisoformat(raw)
            except (ValueError, TypeError):
                last = date(2020, 1, 1)
        else:
            last = date(2020, 1, 1)
        return cls(
            persona_id=d.get("persona_id", ""),
            emotion=d.get("emotion", "calm"),
            energy=d.get("energy", 70),
            today_theme=d.get("today_theme", ""),
            last_updated=last,
        )


# ========== 管理器 ==========

class AIMoodManager:
    """管理 AI 角色每天的心情状态

    用法:
        mgr = AIMoodManager("data/")
        state = mgr.get_or_today("girlfriend_001", relationship_level=60)
        instruction = mgr.get_style_instruction("girlfriend_001")
    """

    def __init__(self, data_dir: str | Path):
        self._data_dir = Path(data_dir)
        self._path = self._data_dir / "ai_mood.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._states: dict[str, AIMoodState] = {}
        self._load()

    @property
    def base_data_dir(self) -> Path:
        return self._data_dir

    # ---- 持久化 ----

    def _load(self):
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                for item in data:
                    state = AIMoodState.from_dict(item)
                    self._states[state.persona_id] = state
        except Exception as e:
            logger.warning(f"Failed to load mood data: {e}")

    def _save(self):
        try:
            data = [s.to_dict() for s in self._states.values()]
            atomic_write_json(self._path, data)
        except Exception as e:
            logger.error(f"Failed to save mood data: {e}")

    # ---- 核心逻辑 ----

    def _compute_daily(self, persona_id: str, relationship_level: int) -> AIMoodState:
        """基于亲密度和随机因子，计算今天的状态"""
        # 亲密度高 → 更倾向正面情绪
        if relationship_level >= 60:
            weights = [0.18, 0.10, 0.15, 0.05, 0.05, 0.17, 0.20, 0.05]
        elif relationship_level >= 30:
            weights = [0.12, 0.18, 0.08, 0.10, 0.10, 0.12, 0.10, 0.15]
        else:
            weights = [0.08, 0.22, 0.05, 0.12, 0.12, 0.08, 0.05, 0.20]

        emotion = random.choices(MOOD_POOL, weights=weights, k=1)[0]

        energy_map = {
            "tired": (20, 55), "melancholy": (25, 60), "quiet": (30, 65),
            "happy": (55, 95), "excited": (60, 100), "playful": (55, 95),
            "affectionate": (50, 90), "calm": (40, 80),
        }
        lo, hi = energy_map.get(emotion, (40, 80))
        energy = random.randint(lo, hi)

        theme_map = {
            "happy": ["想分享快乐", "感觉今天特别美好", "心情好想做点什么"],
            "calm": ["享受安静的一天", "想慢慢聊天"],
            "excited": ["有好多话想说", "充满了分享欲"],
            "tired": ["有点累，想被安慰", "需要一点温暖"],
            "melancholy": ["有点感伤", "想到了过去的事"],
            "playful": ["想逗你开心", "今天特别想皮一下"],
            "affectionate": ["想撒娇", "想要抱抱"],
            "quiet": ["想听你说话", "今天不想说太多"],
        }
        theme = random.choice(theme_map.get(emotion, ["和平常一样"]))

        return AIMoodState(
            persona_id=persona_id,
            emotion=emotion,
            energy=energy,
            today_theme=theme,
            last_updated=date.today(),
        )

    def get_or_today(self, persona_id: str, relationship_level: int = 50) -> AIMoodState:
        """获取或计算今天的状态（当天已有则复用）"""
        today = date.today()
        state = self._states.get(persona_id)
        if state is not None and state.last_updated == today:
            return state

        new_state = self._compute_daily(persona_id, relationship_level)
        self._states[persona_id] = new_state
        self._save()
        return new_state

    def get_style_instruction(self, persona_id: str, relationship_level: int = 50) -> str:
        """生成今天状态描述文本，用于注入 prompt"""
        state = self.get_or_today(persona_id, relationship_level)
        style = MOOD_STYLE.get(state.emotion, "")
        parts = ["【你今天的状态】"]
        if style:
            parts.append(f"心情：{state.emotion}（{style}）")
        else:
            parts.append(f"心情：{state.emotion}")
        if state.energy < 50:
            parts.append(f"今天精力不太好（{state.energy}/100），说话简短些")
        elif state.energy > 85:
            parts.append(f"今天精力充沛（{state.energy}/100），很活跃")
        parts.append(f"内心状态：{state.today_theme}")
        return "\n".join(parts)

    def get_display_summary(self, persona_id: str, relationship_level: int = 50) -> str:
        """给用户看的今日状态摘要"""
        state = self.get_or_today(persona_id, relationship_level)
        emotion_icons = {
            "happy": "😊", "calm": "😌", "excited": "🤩", "tired": "😴",
            "melancholy": "🥺", "playful": "😏", "affectionate": "🥰", "quiet": "🤫",
        }
        icon = emotion_icons.get(state.emotion, "😐")
        emoji = MOOD_STYLE.get(state.emotion, "").split("，")[0] if MOOD_STYLE.get(state.emotion) else ""
        return f"{icon} 今天{emoji}（精力 {state.energy}/100）"
