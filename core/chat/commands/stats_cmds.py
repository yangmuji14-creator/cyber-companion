"""亲密度统计命令：/stats"""

from core.chat.commands.colors import Colors
from core.memory.stats import ChatStats, format_dashboard


async def cmd_stats(handler, cmd: str, user_id: str) -> None:
    """处理 /stats 命令"""
    parts = cmd.split(maxsplit=1)
    sub = parts[1].strip() if len(parts) > 1 else ""

    if sub == "dashboard":
        msgs = handler._h.chat_history.get_messages(user_id)
        stats = ChatStats(msgs)
        print(f"\n{Colors.YELLOW}{format_dashboard(stats)}{Colors.RESET}\n")
        return

    rel_stats = handler._h._affection_storage.get_stats(
        user_id, persona_id=handler._h.current_persona_id
    )
    days = rel_stats.days_known
    level = int(rel_stats.level)
    msgs_total = rel_stats.message_count
    pos = rel_stats.positive_count
    neg = rel_stats.negative_count

    persona = handler._h.persona_loader.get(handler._h.current_persona_id)
    persona_name = persona.name if persona else "她"

    # 新用户（不到 1 天）
    if days == 0:
        print(f"\n{Colors.YELLOW}💕 你和{persona_name}的关系：刚刚认识{Colors.RESET}")
        print(f"  你们才刚相遇呢，一切才刚刚开始。")
        print(f"  多说说话，慢慢了解彼此吧。")
        print(f"\n  {Colors.DIM}仪表盘：/stats dashboard{Colors.RESET}")
        print()
        return

    # 根据亲密度映射关系阶段
    if level >= 80:
        stage = "热恋中 💕"
    elif level >= 60:
        stage = "很亲密 💗"
    elif level >= 40:
        stage = "相处得不错 💛"
    elif level >= 20:
        stage = "慢慢熟悉起来了 🤍"
    else:
        stage = "还不太熟悉 ⬜"

    print(f"\n{Colors.YELLOW}💕 你和{persona_name}的关系：{stage}{Colors.RESET}")

    # 叙事文本 1：基于正/负比例的关系描述
    pos_ratio = pos / max(msgs_total, 1)
    neg_ratio = neg / max(msgs_total, 1)

    if level >= 80:
        if neg_ratio < 0.1:
            print(f"  {persona_name}越来越习惯有你在身边了。")
        else:
            print(f"  虽然偶尔也会闹点小脾气，但从来没真的生过气。")
    elif level >= 60:
        if pos_ratio > 0.5:
            print(f"  和{persona_name}在一起的时光总是很温暖。")
        else:
            print(f"  {persona_name}已经把你当成了很重要的人。")
    elif level >= 40:
        print(f"  你们之间的话题越来越多了，{persona_name}也开始主动找你了。")
    elif level >= 20:
        print(f"  {persona_name}开始对你放下了戒心，偶尔也会开玩笑了。")
    else:
        print(f"  {persona_name}对你还有些陌生，还需要更多时间相处。")

    # 叙事文本 2：基于认识天数的关系历程
    if days < 7:
        print(f"  虽然才认识几天，但已经有了不少回忆。")
    elif days < 30:
        print(f"  认识你 {days} 天了，日子虽短但很珍贵。")
    elif days < 90:
        print(f"  认识你 {days} 天了，每一天都在变得更亲密。")
    elif days < 365:
        print(f"  认识你 {days} 天了，这份感情越来越深了。")
    else:
        years = days // 365
        remainder = days % 365
        print(f"  认识你 {years} 年{remainder} 天了，时间见证了这一切。")

    # 最近情感理解（从最近用户消息中提取）
    msgs_list = handler._h.chat_history.get_messages(user_id)
    for m in reversed(msgs_list):
        if m["role"] == "user" and "emotion_understanding" in m:
            snippet = m["emotion_understanding"]
            if snippet:
                print(f"  {persona_name}觉得：{snippet}")
            break

    print(f"\n  {Colors.DIM}仪表盘：/stats dashboard{Colors.RESET}")
    print()
