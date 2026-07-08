"""记忆相关命令：/memories, /search"""

import json
from datetime import datetime
from pathlib import Path

from core.chat.commands.colors import Colors
from core.memory.storage import MemoryStorage


def _mem_help(handler, user_id: str, parts: list[str]) -> None:
    print(f"\n{Colors.YELLOW}🧠 记忆管理：{Colors.RESET}")
    print(f"  {Colors.CYAN}/memories list [page]{Colors.RESET} — 查看全部记忆（分页）")
    print(f"  {Colors.CYAN}/memories search <关键词>{Colors.RESET} — 搜索记忆")
    print(f"  {Colors.CYAN}/memories add <内容> [等级]{Colors.RESET} — 手动添加记忆（等级 1-5）")
    print(f"  {Colors.CYAN}/memories delete <id>{Colors.RESET} — 删除指定记忆")
    print(f"  {Colors.CYAN}/memories export{Colors.RESET} — 导出所有记忆到 JSON 文件")
    print(f"  {Colors.CYAN}/memories clear --confirm{Colors.RESET} — 清空全部记忆（需确认）")
    print()


def _mem_list(handler, user_id: str, parts: list[str]) -> None:
    page = int(parts[1].strip()) if len(parts) > 1 and parts[1].strip().isdigit() else 1
    per_page = 10
    offset = (page - 1) * per_page
    memories, total = handler._h.memory_mgr.list_all_memories(
        user_id, offset=offset, limit=per_page
    )
    total_pages = max(1, (total + per_page - 1) // per_page)
    if total == 0:
        print(f"\n{Colors.DIM}  还没有关于你的记忆~{Colors.RESET}\n")
        return
    print(f"\n{Colors.YELLOW}🧠 记忆列表（第 {page}/{total_pages} 页，共 {total} 条）：{Colors.RESET}")
    for m in memories:
        stars = "⭐" * m.level
        tags = f" [{', '.join(m.tags)}]" if m.tags else ""
        created = m.created_at[:10] if m.created_at else ""
        print(f"  {Colors.CYAN}{m.id}{Colors.RESET} {stars} {m.content[:60]}{Colors.DIM}{tags} {created}{Colors.RESET}")
    if total_pages > 1:
        print(f"\n  {Colors.DIM}翻页：/memories list {page + 1 if page < total_pages else 1}{Colors.RESET}")
    print()


def _mem_search(handler, user_id: str, parts: list[str]) -> None:
    keyword = parts[1].strip() if len(parts) > 1 else ""
    if not keyword:
        print(f"\n{Colors.DIM}  用法：/memories search <关键词>{Colors.RESET}\n")
        return
    results = handler._h.memory_mgr.search_memories(user_id, keyword)
    if not results:
        print(f"\n{Colors.DIM}  未找到包含「{keyword}」的记忆{Colors.RESET}\n")
    else:
        print(f"\n{Colors.YELLOW}🔍 搜索「{keyword}」找到 {len(results)} 条记忆：{Colors.RESET}")
        for m in results:
            stars = "⭐" * m.level
            print(f"  {Colors.CYAN}{m.id}{Colors.RESET} {stars} {m.content[:60]}")
        print()


def _mem_add(handler, user_id: str, parts: list[str]) -> None:
    if len(parts) < 2 or not parts[1].strip():
        print(f"\n{Colors.DIM}  用法：/memories add <内容> [等级1-5]{Colors.RESET}\n")
        return
    add_parts = parts[1].strip().rsplit(maxsplit=1)
    content = add_parts[0]
    level = None
    if len(add_parts) > 1 and add_parts[1].isdigit():
        level = max(1, min(5, int(add_parts[1])))
    mem = handler._h.memory_mgr.add_memory_sync(user_id, content, level=level)
    if mem:
        print(f"\n{Colors.GREEN}✅ 已添加记忆 {mem.id}（等级 {mem.level}）：{mem.content[:40]}{Colors.RESET}\n")
    else:
        print(f"\n{Colors.DIM}  记忆内容太简单，没有记住~（评分 < 2）{Colors.RESET}\n")


def _mem_delete(handler, user_id: str, parts: list[str]) -> None:
    if len(parts) < 2 or not parts[1].strip():
        print(f"\n{Colors.DIM}  用法：/memories delete <记忆id>{Colors.RESET}\n")
        return
    mid = parts[1].strip()
    if handler._h.memory_mgr.delete_memory(user_id, mid):
        print(f"\n{Colors.GREEN}✅ 已删除记忆 {mid}{Colors.RESET}\n")
    else:
        print(f"\n{Colors.DIM}  未找到记忆 {mid}{Colors.RESET}\n")


def _mem_export(handler, user_id: str, parts: list[str]) -> None:
    all_ms = handler._h.memory_mgr.export_memories(user_id)
    if not all_ms:
        print(f"\n{Colors.DIM}  还没有记忆可以导出~{Colors.RESET}\n")
        return
    data = {
        "user_id": user_id,
        "count": len(all_ms),
        "memories": [
            {"id": m.id, "content": m.content, "level": m.level,
             "tags": m.tags, "created_at": m.created_at}
            for m in all_ms
        ],
    }
    export_path = Path(handler._h.memory_mgr.data_dir) / f"memories_{user_id}.json"
    with open(export_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n{Colors.GREEN}✅ 已导出 {len(all_ms)} 条记忆到 {export_path}{Colors.RESET}\n")


def _mem_clear(handler, user_id: str, parts: list[str]) -> None:
    all_ms = handler._h.memory_mgr.export_memories(user_id)
    if not all_ms:
        print(f"\n{Colors.DIM}  已经没有记忆了~{Colors.RESET}\n")
        return
    rest = parts[1].strip() if len(parts) > 1 else ""
    if "--confirm" not in rest:
        print(f"\n{Colors.YELLOW}⚠ 这会清空全部 {len(all_ms)} 条记忆，无法恢复{Colors.RESET}")
        print(f"  {Colors.DIM}输入 /memories clear --confirm 确认清空{Colors.RESET}")
        print(f"  {Colors.DIM}输入 /memories export 先备份记忆{Colors.RESET}\n")
        return
    storage = MemoryStorage(str(handler._h.memory_mgr.data_dir))
    storage.delete_all(user_id)
    print(f"\n{Colors.GREEN}✅ 已清空全部 {len(all_ms)} 条记忆{Colors.RESET}\n")


_MEMORY_DISPATCH = {
    "help": _mem_help,
    "list": _mem_list,
    "search": _mem_search,
    "add": _mem_add,
    "delete": _mem_delete,
    "export": _mem_export,
    "clear": _mem_clear,
}


async def cmd_memories(handler, user_id: str, sub: str) -> None:
    """处理 /memories 命令"""
    parts = sub.split(maxsplit=1)
    action = parts[0] if parts else "list"

    action_handler = _MEMORY_DISPATCH.get(action)
    if action_handler:
        action_handler(handler, user_id, parts)
    else:
        print(f"\n{Colors.DIM}  未知操作：{action}，输入 /memories help 查看帮助{Colors.RESET}\n")


def cmd_search(handler, user_id: str, keyword: str) -> None:
    """搜索聊天历史"""
    if not keyword:
        print(f"\n{Colors.YELLOW}用法：/search <关键词>{Colors.RESET}")
        print(f"  {Colors.DIM}示例：/search 生日{Colors.RESET}\n")
        return
    results = handler._h.chat_history.search_messages(user_id, keyword)
    if not results:
        print(f"\n{Colors.DIM}  未找到包含「{keyword}」的消息{Colors.RESET}\n")
        return
    print(f"\n{Colors.YELLOW}🔍 搜索「{keyword}」找到 {len(results)} 条结果：{Colors.RESET}")
    for r in results:
        msg = r["message"]
        before = r["before"]
        after = r["after"]
        role_icon = "🧑" if msg["role"] == "user" else "💕"
        ts = msg.get("timestamp", "")
        time_str = ""
        if ts:
            try:
                dt = datetime.fromisoformat(ts)
                time_str = f" {Colors.DIM}{dt.strftime('%m-%d %H:%M')}{Colors.RESET}"
            except (ValueError, TypeError):
                pass
        if before:
            b_role = "🧑" if before["role"] == "user" else "💕"
            b_preview = before["content"][:30] + ("..." if len(before["content"]) > 30 else "")
            print(f"  {Colors.DIM}{b_role} {b_preview}{Colors.RESET}")
        content = msg["content"]
        highlighted = content.replace(keyword, f"{Colors.YELLOW}{keyword}{Colors.RESET}")
        print(f"  {Colors.CYAN}[#{r['index']}]{Colors.RESET} {role_icon}{time_str} {highlighted}")
        if after:
            a_role = "🧑" if after["role"] == "user" else "💕"
            a_preview = after["content"][:30] + ("..." if len(after["content"]) > 30 else "")
            print(f"  {Colors.DIM}{a_role} {a_preview}{Colors.RESET}")
        print()
