"""系统命令：/help, /clear, /debug, /quit, /undo"""

from core.chat.commands.colors import Colors
from core.chat.commands.registry import COMMANDS


def cmd_help(handler) -> None:
    """显示可用命令"""
    print(f"\n{Colors.YELLOW}📖 可用命令：{Colors.RESET}")
    for name, desc in COMMANDS.items():
        print(f"  {Colors.CYAN}{name}{Colors.RESET} — {desc}")
    print()


def cmd_clear(handler, user_id: str, cmd: str) -> None:
    """清空聊天历史"""
    if cmd == "/clear":
        msgs = handler._h.chat_history.get_messages(user_id)
        count = len(msgs)
        print(f"\n{Colors.YELLOW}⚠ 这会清空所有聊天历史（{count} 条消息），无法恢复{Colors.RESET}")
        print(f"  {Colors.DIM}输入 /clear --confirm 确认清空，或 /export 先备份{Colors.RESET}\n")
        return
    handler._h.chat_history.delete_user(user_id)
    print(f"\n{Colors.GREEN}✅ 聊天历史已清空{Colors.RESET}\n")


def cmd_debug(handler) -> None:
    """查看当前 system prompt"""
    prompt = handler._h.pipeline.get_last_system_prompt()
    if prompt:
        print(f"\n{Colors.YELLOW}🔧 当前 System Prompt：{Colors.RESET}")
        print(f"{Colors.DIM}{'─' * 50}{Colors.RESET}")
        for line in prompt.split("\n"):
            print(f"  {line}")
        print(f"{Colors.DIM}{'─' * 50}{Colors.RESET}")
        print(f"  {Colors.DIM}共 {len(prompt)} 字符{Colors.RESET}\n")
    else:
        print(f"\n{Colors.YELLOW}🔧 人设配置（尚未生成完整 System Prompt）：{Colors.RESET}")
        print(f"{Colors.DIM}{'─' * 50}{Colors.RESET}")
        persona = handler._h.persona_loader.get(handler._h.current_persona_id)
        if persona:
            print(f"  {Colors.DIM}ID：{persona.id}{Colors.RESET}")
            print(f"  {Colors.DIM}名字：{persona.name}{Colors.RESET}")
            print(f"  {Colors.DIM}年龄：{persona.age}{Colors.RESET}")
            print(f"  {Colors.DIM}性别：{persona.gender}{Colors.RESET}")
            if persona.personality:
                print(f"  {Colors.DIM}性格：{', '.join(persona.personality)}{Colors.RESET}")
            if persona.mbti:
                print(f"  {Colors.DIM}MBTI：{persona.mbti}{Colors.RESET}")
            if persona.background:
                print(f"  {Colors.DIM}背景：{persona.background}{Colors.RESET}")
            if persona.system_prompt:
                print(f"  {Colors.DIM}自定义 System Prompt：{Colors.RESET}")
                for line in persona.system_prompt.split("\n"):
                    print(f"    {line}")
            print(f"{Colors.DIM}{'─' * 50}{Colors.RESET}")
            print(f"  {Colors.DIM}提示：发送消息后可用 /debug 查看完整 System Prompt{Colors.RESET}\n")
        else:
            print(f"  {Colors.DIM}人设未加载（current_persona_id={handler._h.current_persona_id}）{Colors.RESET}\n")


def cmd_undo(handler, user_id: str) -> None:
    """撤销上一轮对话（删除最后一条用户消息和 AI 回复）"""
    msgs = handler._h.chat_history.get_messages(user_id)
    if len(msgs) < 2:
        print(f"\n{Colors.DIM}  没有可以撤销的消息{Colors.RESET}\n")
        return
    if msgs[-1]["role"] != "assistant" or msgs[-2]["role"] != "user":
        print(f"\n{Colors.YELLOW}⚠ 最后两条消息不是完整的对话轮次，跳过{Colors.RESET}\n")
        return
    deleted = handler._h.chat_history.delete_last_messages(user_id, 2)
    print(f"\n{Colors.GREEN}✅ 已撤销最后 {len(deleted)} 条消息{Colors.RESET}")
    for msg in deleted:
        role = "🧑" if msg["role"] == "user" else "💕"
        preview = msg["content"][:40] + ("..." if len(msg["content"]) > 40 else "")
        print(f"  {Colors.DIM}{role} {preview}{Colors.RESET}")
    print()
