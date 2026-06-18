"""ThoughtOrganizer — 将 BrainInput 状态组织为内心独白碎片（念头）

接收 StateCollector 聚合的 BrainInput，将其中的每个非 None 字段
转换为一条 MonologueThought（第一人称、带优先级/分类），
按优先级排序后返回列表。

用法:
    organizer = ThoughtOrganizer(max_tokens=1000)
    thoughts = organizer.organize(brain_input)
"""

from __future__ import annotations

from typing import List

from .models import BrainInput, MonologueThought


class ThoughtOrganizer:
    """状态 → 念头 转换器

    将 BrainInput 中的各个字段按规则转换为 MonologueThought 列表。
    纯规则驱动，不调用任何 LLM。
    """

    def __init__(self, max_tokens: int = 1000):
        self.max_tokens = max_tokens

    def organize(self, brain_input: BrainInput) -> List[MonologueThought]:
        """将 BrainInput 转换为有序的念头列表

        Args:
            brain_input: 聚合了各子系统状态的 BrainInput

        Returns:
            按优先级降序排列的 MonologueThought 列表，自动截断超长内容
        """
        thoughts: List[MonologueThought] = []

        # 1. Feeling — 情绪反应（最高优先级）
        mood_thought = self._build_mood_thought(brain_input)
        if mood_thought:
            thoughts.append(mood_thought)

        # 2. Intention — 对话意图 + 开放式循环待办
        thoughts.extend(self._build_intention_thoughts(brain_input))

        # 3. Observation — 当前对话感知
        thoughts.extend(self._build_observation_thoughts(brain_input))

        # 4. Memory — 长期信息
        thoughts.extend(self._build_memory_thoughts(brain_input))

        # 5. Disposition — 稳定特质
        thoughts.extend(self._build_disposition_thoughts(brain_input))

        # 6. Context — 环境信息（最低优先级）
        thoughts.extend(self._build_context_thoughts(brain_input))

        # 按优先级降序排列
        thoughts.sort(key=lambda t: t.priority, reverse=True)

        # 截断超长内容
        thoughts = self._truncate(thoughts)

        # 确保至少有一条默认念头
        if not thoughts:
            thoughts = [
                MonologueThought(
                    source="brain",
                    content="此时我心里很平静。",
                    priority=0.1,
                    category="observation",
                )
            ]

        return thoughts

    # ────────── 1. Feeling ──────────

    def _build_mood_thought(self, bi: BrainInput) -> MonologueThought | None:
        """根据情绪 valence/arousal 生成情感反应念头"""
        valence = bi.mood_valence
        arousal = bi.mood_arousal
        if valence is None and arousal is None:
            return None

        # 确定情绪文本
        if valence is not None and valence > 0.5:
            if arousal is not None and arousal > 0.5:
                text = "我心情不错，感觉有点兴奋"
            else:
                text = "我心情不错，感觉很放松"
        elif valence is not None and valence <= 0.3:
            if arousal is not None and arousal > 0.5:
                text = "我心里有点闷，又有点烦躁"
            else:
                text = "我心里有点闷，不太想说话"
        elif valence is not None:
            text = "我心情还算平静"
        else:
            # 只有 arousal
            if arousal is not None and arousal > 0.5:
                text = "我感觉有点兴奋"
            else:
                text = "我有点提不起劲"

        # 优先级: 0.8-1.0，用 intensity 微调
        intensity = bi.mood_intensity if bi.mood_intensity is not None else 0.5
        priority = min(1.0, 0.8 + intensity * 0.2)

        return MonologueThought(
            source="mood", content=text, priority=priority, category="feeling"
        )

    # ────────── 2. Intention ──────────

    def _build_intention_thoughts(self, bi: BrainInput) -> List[MonologueThought]:
        """根据 OpenLoop 事件和对话思考生成意图念头"""
        thoughts: List[MonologueThought] = []

        # OpenLoop 事件 → 最多一条
        if bi.openloop_events:
            event = bi.openloop_events[0]
            cleaned = event.replace("（待完成）", "").replace("(待完成)", "").strip()
            thoughts.append(
                MonologueThought(
                    source="openloop",
                    content=f"我记得他{cleaned}",
                    priority=0.75,
                    category="intention",
                )
            )

        # 对话思考 → 最多一条
        if bi.dialogue_thought:
            thoughts.append(
                MonologueThought(
                    source="dialogue",
                    content="我在想他刚才说的话……",
                    priority=0.7,
                    category="intention",
                )
            )

        return thoughts

    # ────────── 3. Observation ──────────

    def _build_observation_thoughts(self, bi: BrainInput) -> List[MonologueThought]:
        """根据当前话题、用户情绪、时段生成观察念头"""
        thoughts: List[MonologueThought] = []

        # 当前话题
        if bi.current_topic:
            thoughts.append(
                MonologueThought(
                    source="topic",
                    content=f"我们在聊他{bi.current_topic}的事",
                    priority=0.6,
                    category="observation",
                )
            )

        # 用户情绪
        if bi.user_emotion:
            sad_emotions = {
                "sad", "tired", "depressed", "lonely",
                "anxious", "angry", "frustrated",
            }
            happy_emotions = {
                "happy", "excited", "grateful", "love", "ecstatic",
            }
            emo = bi.user_emotion.lower()
            if emo in sad_emotions:
                text = "他好像不太开心……"
            elif emo in happy_emotions:
                text = "他心情不错，我也跟着开心"
            else:
                text = f"他好像{bi.user_emotion}的样子"
            thoughts.append(
                MonologueThought(
                    source="user_emotion",
                    content=text,
                    priority=0.55,
                    category="observation",
                )
            )

        return thoughts

    # ────────── 4. Memory ──────────

    def _build_memory_thoughts(self, bi: BrainInput) -> List[MonologueThought]:
        """根据身份信息和人生总结生成记忆念头"""
        thoughts: List[MonologueThought] = []

        # 身份信息
        if bi.identity_context:
            text = self._extract_identity_text(bi.identity_context)
            thoughts.append(
                MonologueThought(
                    source="identity",
                    content=text,
                    priority=0.5,
                    category="memory",
                )
            )

        # 人生总结
        if bi.life_summary:
            text = self._extract_life_summary_text(bi.life_summary)
            thoughts.append(
                MonologueThought(
                    source="life_summary",
                    content=text,
                    priority=0.45,
                    category="memory",
                )
            )

        return thoughts

    @staticmethod
    def _extract_identity_text(identity_context: str) -> str:
        """从身份上下文中提取有意义的描述文本"""
        lines = [
            l.strip().lstrip("- ").strip()
            for l in identity_context.split("\n")
            if l.strip() and not l.strip().startswith("【")
        ]
        if not lines:
            return "我记得他的一些事"

        line = lines[0]
        # 尝试提取 "：" 后的内容
        if "：" in line:
            parts = line.split("：", 1)
            value = parts[1].strip()
            if value:
                return f"我记得他是{value}"
        return f"我记得{line}"

    @staticmethod
    def _extract_life_summary_text(life_summary: str) -> str:
        """从人生总结中提取有意义的描述文本"""
        lines = [
            l.strip().lstrip("- ").strip()
            for l in life_summary.split("\n")
            if l.strip() and not l.strip().startswith("【")
        ]
        if not lines:
            return "他最近好像挺忙的"

        line = lines[0]
        # 尝试提取 "：" 后的内容
        if "：" in line:
            parts = line.split("：", 1)
            value = parts[1].strip()
            if value:
                return f"他最近{value}"
        return f"他最近{line}"

    # ────────── 5. Disposition ──────────

    def _build_disposition_thoughts(self, bi: BrainInput) -> List[MonologueThought]:
        """根据人格维度、亲密度、人设生成特质念头"""
        thoughts: List[MonologueThought] = []

        # 人格维度（source='personality'）→ 合并为一条
        personality_parts: List[str] = []
        if bi.personality_trust is not None and bi.personality_trust > 0.6:
            personality_parts.append("我很信任他")
        if bi.personality_jealousy is not None and bi.personality_jealousy > 0.6:
            personality_parts.append("他提到别人的时候我有点在意")
        if bi.personality_dependence is not None and bi.personality_dependence > 0.6:
            personality_parts.append("我有点依赖他")
        if bi.personality_openness is not None and bi.personality_openness > 0.6:
            personality_parts.append("我对他很开放")
        if bi.personality_affection is not None and bi.personality_affection > 0.6:
            personality_parts.append("我喜欢和他在一起")

        if personality_parts:
            thoughts.append(
                MonologueThought(
                    source="personality",
                    content="，".join(personality_parts),
                    priority=0.4,
                    category="concern",
                )
            )

        # 亲密度（source='affection'）
        if bi.affection_level is not None:
            if bi.affection_level > 50:
                text = "我感觉跟他越来越亲近了"
            elif bi.affection_level < 30:
                text = "我们还不太熟"
            else:
                text = "我和他相处得还不错"
            thoughts.append(
                MonologueThought(
                    source="affection",
                    content=text,
                    priority=0.35,
                    category="concern",
                )
            )

        # 人设特质（source='persona'）→ 合并为一条
        persona_parts: List[str] = []
        if bi.persona_traits:
            for trait in bi.persona_traits:
                if trait in ("活泼", "开朗", "外向"):
                    persona_parts.append("我平时还是挺活泼的")
                    break
            for trait in bi.persona_traits:
                if trait in ("粘人", "依赖"):
                    persona_parts.append("我是有点粘人")
                    break
        if persona_parts:
            thoughts.append(
                MonologueThought(
                    source="persona",
                    content="，".join(persona_parts),
                    priority=0.3,
                    category="observation",
                )
            )

        return thoughts

    # ────────── 6. Context ──────────

    def _build_context_thoughts(self, bi: BrainInput) -> List[MonologueThought]:
        """根据主动行为统计和时段生成环境上下文念头"""
        thoughts: List[MonologueThought] = []

        # 时段（环境上下文，低优先级）
        if bi.time_period:
            period_texts = {
                "late_night": "这么晚了他还没睡……",
                "morning": "早上了，新的一天",
                "afternoon": "下午了",
                "evening": "晚上了",
                "night": "夜深了",
            }
            text = period_texts.get(bi.time_period, f"现在是{bi.time_period}")
            thoughts.append(
                MonologueThought(
                    source="time",
                    content=text,
                    priority=0.2,
                    category="observation",
                )
            )

        # 主动联系统计
        if bi.proactive_times_today is not None and bi.proactive_times_today > 0:
            thoughts.append(
                MonologueThought(
                    source="proactive",
                    content=f"今天已经找了他{bi.proactive_times_today}次了",
                    priority=0.15,
                    category="observation",
                )
            )

        return thoughts

    # ────────── Truncation ──────────

    def _truncate(self, thoughts: List[MonologueThought]) -> List[MonologueThought]:
        """按 token 预算截断，移除低优先级念头

        Token 估算：len(content) // 2（中文字符 ≈ 1 token）
        至少保留一条念头。
        """
        if not thoughts:
            return []

        total_tokens = sum(max(1, len(t.content) // 2) for t in thoughts)
        if total_tokens <= self.max_tokens:
            return thoughts

        # 按优先级降序排列后，优先保留高优先级
        sorted_thoughts = sorted(thoughts, key=lambda t: t.priority, reverse=True)
        result: List[MonologueThought] = []
        total = 0
        for t in sorted_thoughts:
            tokens = max(1, len(t.content) // 2)
            if total + tokens <= self.max_tokens:
                result.append(t)
                total += tokens
            elif not result:
                # 至少保留一条
                result.append(t)
                break
            else:
                break

        return result
