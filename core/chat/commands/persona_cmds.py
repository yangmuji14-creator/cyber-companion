"""人设 / 人格 / 情绪命令：/persona, /personality, /mood"""

from collections import Counter

from core.chat.commands.colors import Colors
from core.emotion.mood import MOOD_EMOJI_MAP, MoodType


# 情绪 emoji 映射 — 统一使用 MoodEngine 的 MOOD_EMOJI_MAP
_EMOTION_TO_MOOD_NAME = {
    "happy": "happy", "sad": "sad", "angry": "angry",
    "neutral": "neutral", "excited": "excited", "lonely": "lonely",
    "anxious": "anxious", "love": "love",
}


def _get_mood_emoji(emotion_name: str) -> str:
    """获取情绪对应的 emoji，使用 MoodEngine 的统一映射"""
    try:
        mood_name = _EMOTION_TO_MOOD_NAME.get(emotion_name, "neutral")
        mt = MoodType(mood_name)
        return MOOD_EMOJI_MAP.get(mt, "😐")
    except (ValueError, AttributeError):
        return "😐"


def cmd_persona(handler, user_id: str, sub: str) -> None:
    """处理 /persona 命令"""
    parts = sub.split(maxsplit=1) if sub else []

    if sub == "list":
        all_p = handler._h.persona_loader.list_all()
        if not all_p:
            print(f"\n{Colors.DIM}  没有可用的人设{Colors.RESET}\n")
            return
        print(f"\n{Colors.YELLOW}🎀 人设列表：{Colors.RESET}")
        for p in all_p:
            marker = f" {Colors.GREEN}<- 当前{Colors.RESET}" if p.id == handler._h.current_persona_id else ""
            mbti = f" [{p.mbti}]" if p.mbti else ""
            traits = f" {'、'.join(p.personality[:3])}" if p.personality else ""
            print(f"  {Colors.CYAN}{p.id}{Colors.RESET} - {p.name}（{p.age}岁{mbti}）{traits}{marker}")
        print(f"\n  {Colors.DIM}切换：/persona switch <id>{Colors.RESET}\n")
        return

    if parts and parts[0] == "switch":
        if len(parts) < 2 or not parts[1]:
            print(f"\n{Colors.DIM}  用法：/persona switch <id>{Colors.RESET}\n")
            return
        target_id = parts[1].strip()
        target = handler._h.persona_loader.get(target_id)
        if not target:
            print(f"\n{Colors.DIM}  未找到人设 {target_id}{Colors.RESET}\n")
            return
        if target_id == handler._h.current_persona_id:
            print(f"\n{Colors.DIM}  已经在使用 {target.name} 了~{Colors.RESET}\n")
            return
        handler._h.current_persona_id = target_id
        print(f"\n{Colors.GREEN}✅ 已切换到 {target.name}（{target.id}）{Colors.RESET}")
        level = int(handler._h._affection_storage.get_level(
            user_id, persona_id=target_id
        ))
        print(f"  {Colors.DIM}💕 与 {target.name} 的亲密度：{level}/100{Colors.RESET}\n")
        return

    # 默认显示当前人设详情
    p = handler._h.persona_loader.get(handler._h.current_persona_id)
    if p:
        print(f"\n{Colors.YELLOW}🎀 人设信息{Colors.RESET}")
        print(f"  名字：{p.name}")
        print(f"  年龄：{p.age}岁")
        if p.personality:
            print(f"  性格：{'、'.join(p.personality)}")
        if p.hobbies:
            hobbies = [h.get("name", "") for h in p.hobbies[:3]]
            print(f"  爱好：{'、'.join(hobbies)}")
        if p.catchphrases:
            print(f"  口头禅：{'、'.join(p.catchphrases)}")
        print(f"\n  {Colors.DIM}人设列表：/persona list | 切换：/persona switch <id>{Colors.RESET}\n")


def cmd_personality(handler, user_id: str) -> None:
    """查看当前人格状态"""
    pe = getattr(handler._h, '_personality_engine', None)
    if not pe:
        print(f"\n{Colors.DIM}  人格引擎未启用{Colors.RESET}\n")
        return
    state = pe.get_state(user_id)
    traits = [
        ("信任度", state.trust, "❤️"),
        ("依赖度", state.dependence, "🤗"),
        ("开放度", state.openness, "💬"),
        ("好感度", state.affection, "💕"),
        ("醋意值", state.jealousy, "😤"),
    ]
    print(f"\n{Colors.YELLOW}🧠 人格状态{Colors.RESET}")
    for label, value, emoji in traits:
        bar_len = int(value * 10)
        bar = "█" * bar_len + "░" * (10 - bar_len)
        print(f"  {emoji} {label}：{bar} {value:.0%}")
    print(f"\n  {Colors.CYAN}交互统计：{Colors.RESET}")
    print(f"  总互动：{state.total_interactions} 次")
    print(f"  正面：👍 {state.positive_count} / 负面：👎 {state.negative_count}")
    print()


def cmd_mood(handler, user_id: str) -> None:
    """查看当前情绪状态（含 Mood 引擎数据）"""
    msgs = handler._h.chat_history.get_messages(user_id)
    user_msgs = [m for m in msgs if m["role"] == "user" and "emotion" in m]
    total = len(user_msgs)

    print(f"\n{Colors.YELLOW}🎭 情绪状态{Colors.RESET}")

    # Mood 引擎数据（新增）
    mood_engine = getattr(handler._h, '_mood_engine', None)
    if mood_engine:
        mood = mood_engine.get_mood(user_id)
        mood_emoji = mood_engine.get_mood_emoji(user_id)
        mood_ctx = mood_engine.get_mood_context(user_id)
        bar_len = 10
        filled = round(mood.energy * bar_len)
        energy_bar = "█" * filled + "░" * (bar_len - filled)
        print(f"  {mood_emoji} Mood：{mood.mood.value}（强度 {mood.intensity:.0%}）")
        print(f"  ⚡ 精力：{energy_bar} {mood.energy:.0%}")
        print(f"  📊 效价 {mood.valence:+.2f} / 唤醒 {mood.arousal:.2f}")
        print(f"  {Colors.DIM}{mood_ctx}{Colors.RESET}\n")
    else:
        print(f"  {Colors.DIM}Mood 引擎未启用{Colors.RESET}\n")

    if user_msgs:
        emotions = Counter(m["emotion"] for m in user_msgs)
        latest = user_msgs[-1]
        latest_emoji = _get_mood_emoji(latest["emotion"])
        latest_intensity = latest.get("emotion_intensity", 0)
        print(f"  最近消息情绪：{latest_emoji} {latest['emotion']}（强度 {latest_intensity:.0%}）")
        print(f"  {Colors.DIM}基于最近 {total} 条消息{Colors.RESET}\n")
        print(f"  {Colors.CYAN}情绪分布：{Colors.RESET}")
        for emotion, count in emotions.most_common():
            icon = _get_mood_emoji(emotion)
            pct = count / total * 100
            bar_len = int(pct / 5)
            bar = "█" * bar_len + "░" * (20 - bar_len)
            print(f"  {icon} {emotion:8s} {bar} {count}次 ({pct:.0f}%)")
    print()
