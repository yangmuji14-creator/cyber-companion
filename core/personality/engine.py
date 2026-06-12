"""PersonalityEngine — 人格成长引擎

根据交互动态更新人格状态：
- 聊天时长 → 影响信任度、依赖度
- 聊天频率 → 影响依赖度
- 情绪分布 → 影响喜爱度、嫉妒度
- 关系等级 → 影响整体成长速度
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger

from core.utils import atomic_write_json
from .models import PersonalityState


class PersonalityEngine:
    """人格成长引擎"""

    def __init__(self, data_dir: str | Path):
        self._data_dir = Path(data_dir)
        self._path = self._data_dir / "personality_states.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._states: dict[str, PersonalityState] = {}
        self._load()

    def _load(self):
        """加载持久化数据"""
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                for item in data:
                    state = PersonalityState.from_dict(item)
                    self._states[state.persona_id] = state
            logger.debug(f"Loaded {len(self._states)} personality states")
        except Exception as e:
            logger.warning(f"Failed to load personality data: {e}")

    def _save(self):
        """持久化到文件"""
        try:
            data = [s.to_dict() for s in self._states.values()]
            atomic_write_json(self._path, data)
        except Exception as e:
            logger.error(f"Failed to save personality data: {e}")

    def get_state(self, persona_id: str) -> PersonalityState:
        """获取人格状态（不存在则创建默认）"""
        if persona_id not in self._states:
            self._states[persona_id] = PersonalityState(persona_id=persona_id)
            self._save()
        return self._states[persona_id]

    def update_on_message(
        self,
        persona_id: str,
        emotion: str,
        relationship_level: int,
        session_duration_minutes: float = 0.0,
    ) -> PersonalityState:
        """处理一条消息后更新人格状态

        Args:
            persona_id: 角色 ID
            emotion: 当前情绪（happy, sad, angry 等）
            relationship_level: 当前关系等级（0-100）
            session_duration_minutes: 本次会话时长（分钟）

        Returns:
            更新后的人格状态
        """
        state = self.get_state(persona_id)

        # 更新统计
        state.total_messages += 1
        state.last_interaction = datetime.now().isoformat()

        if session_duration_minutes > 0:
            state.total_duration_minutes += int(session_duration_minutes)
            state.avg_session_length = (
                state.total_duration_minutes / max(1, state.total_sessions)
            )

        # 记录情绪
        state.emotion_history.append(emotion)
        if len(state.emotion_history) > 20:
            state.emotion_history = state.emotion_history[-20:]

        # 计算成长系数（关系等级越高，成长越快）
        growth_factor = 0.5 + (relationship_level / 100) * 0.5

        # === 更新五维人格 ===

        # 1. 信任度：受聊天时长和频率影响
        if session_duration_minutes > 10:
            trust_boost = min(2.0, session_duration_minutes * 0.1) * growth_factor
            state.trust = min(100, state.trust + trust_boost)

        # 2. 依赖度：受聊天频率影响
        if state.total_sessions > 5:
            dependence_boost = 0.3 * growth_factor
            state.dependence = min(100, state.dependence + dependence_boost)

        # 3. 开放度：受情绪多样性影响
        unique_emotions = len(set(state.emotion_history[-10:]))
        if unique_emotions >= 3:
            openness_boost = 0.2 * growth_factor
            state.openness = min(100, state.openness + openness_boost)

        # 4. 喜爱度：受正面情绪影响
        positive_emotions = {"happy", "excited", "affectionate", "playful"}
        recent_positive = sum(
            1 for e in state.emotion_history[-10:] if e in positive_emotions
        )
        if recent_positive >= 3:
            affection_boost = 0.4 * growth_factor
            state.affection = min(100, state.affection + affection_boost)

        # 5. 嫉妒度：受负面情绪和关系等级影响
        negative_emotions = {"sad", "angry", "melancholy"}
        recent_negative = sum(
            1 for e in state.emotion_history[-10:] if e in negative_emotions
        )
        if recent_negative >= 2 and relationship_level < 50:
            jealousy_boost = 0.2
            state.jealousy = min(100, state.jealousy + jealousy_boost)
        elif relationship_level >= 70:
            # 高亲密度时嫉妒度缓慢下降
            state.jealousy = max(0, state.jealousy - 0.1)

        # 自然衰减（所有维度缓慢回归中间值）
        self._natural_decay(state)

        state.updated_at = datetime.now().isoformat()
        self._save()

        logger.debug(
            f"Updated personality for {persona_id}: "
            f"trust={state.trust:.1f} depend={state.dependence:.1f} "
            f"open={state.openness:.1f} affect={state.affection:.1f} "
            f"jealous={state.jealousy:.1f}"
        )

        return state

    def update_on_session_start(self, persona_id: str) -> PersonalityState:
        """会话开始时调用，更新会话计数"""
        state = self.get_state(persona_id)
        state.total_sessions += 1

        # 检查是否是新的一天（影响依赖度）
        if state.last_interaction:
            try:
                last = datetime.fromisoformat(state.last_interaction)
                if datetime.now().date() > last.date():
                    # 新的一天，依赖度略微增加
                    state.dependence = min(100, state.dependence + 0.5)
            except (ValueError, TypeError):
                pass

        state.updated_at = datetime.now().isoformat()
        self._save()
        return state

    def _natural_decay(self, state: PersonalityState):
        """自然衰减：所有维度缓慢回归中间值"""
        decay_rate = 0.02  # 衰减率

        # 信任度、依赖度、喜爱度：低于50时缓慢上升，高于50时缓慢下降
        for attr in ["trust", "dependence", "affection"]:
            current = getattr(state, attr)
            if current < 50:
                setattr(state, attr, min(50, current + decay_rate))
            elif current > 50:
                setattr(state, attr, max(50, current - decay_rate))

        # 开放度：缓慢向60靠拢
        if state.openness < 60:
            state.openness = min(60, state.openness + decay_rate * 0.5)
        elif state.openness > 60:
            state.openness = max(60, state.openness - decay_rate * 0.5)

        # 嫉妒度：缓慢向30靠拢
        if state.jealousy < 30:
            state.jealousy = min(30, state.jealousy + decay_rate * 0.3)
        elif state.jealousy > 30:
            state.jealousy = max(30, state.jealousy - decay_rate * 0.3)

    def get_growth_summary(self, persona_id: str) -> str:
        """生成人格成长摘要（给用户看）"""
        state = self.get_state(persona_id)

        def describe_level(value: float) -> str:
            if value < 20:
                return "很低"
            elif value < 40:
                return "较低"
            elif value < 60:
                return "中等"
            elif value < 80:
                return "较高"
            else:
                return "很高"

        lines = ["【人格成长状态】"]
        lines.append(f"信任度: {describe_level(state.trust)} ({state.trust:.0f}/100)")
        lines.append(f"依赖度: {describe_level(state.dependence)} ({state.dependence:.0f}/100)")
        lines.append(f"开放度: {describe_level(state.openness)} ({state.openness:.0f}/100)")
        lines.append(f"喜爱度: {describe_level(state.affection)} ({state.affection:.0f}/100)")
        lines.append(f"嫉妒度: {describe_level(state.jealousy)} ({state.jealousy:.0f}/100)")
        lines.append(f"\n共聊天 {state.total_messages} 条消息，{state.total_sessions} 次会话")

        return "\n".join(lines)

    def reset_state(self, persona_id: str) -> PersonalityState:
        """重置人格状态"""
        state = PersonalityState(persona_id=persona_id)
        self._states[persona_id] = state
        self._save()
        return state
