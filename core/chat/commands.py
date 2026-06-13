"""CommandHandler — 斜杠命令系统

处理所有 / 开头的斜杠命令：
  /help /stats /memories /persona /debug /clear /export
  /undo /regen /search /mood /quit
"""

import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from loguru import logger

from core.chat.pipeline import get_llm_error_message
from core.emotion.mood import MOOD_EMOJI_MAP, MoodType
from core.memory.stats import ChatStats, format_dashboard
from core.memory.storage import MemoryStorage
from core.multimodal import ImageHandler


# ========== 命令表 ==========

COMMANDS = {
    "/help": "显示可用命令",
    "/stats": "亲密度统计（/stats dashboard 看仪表盘）",
    "/memories": "记忆管理（/memories help 查看帮助）",
    "/persona": "人设管理（/persona list 查看所有人设）",
    "/debug": "查看当前 system prompt",
    "/clear": "清空聊天历史",
    "/export": "导出聊天记录（/export md 或 /export json）",
    "/undo": "撤销上一轮对话（删除最后一条用户消息和 AI 回复）",
    "/regen": "让 AI 重新生成上一条回复",
    "/search": "搜索聊天历史（/search <关键词>）",
    "/mood": "查看当前情绪状态（含 Mood 引擎数据）",
    "/personality": "查看当前人格状态",
    "/tools": "查看可用工具列表",
    "/img": "发送图片，AI 识别并回复内容",
    "/quit": "退出聊天",
}

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


# ========== ANSI 颜色 ==========

class Colors:
    """ANSI 颜色码（Windows 10+ 原生支持）"""
    CYAN = "\033[36m"
    MAGENTA = "\033[35m"
    YELLOW = "\033[33m"
    GREEN = "\033[32m"
    RED = "\033[31m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


# ========== CommandHandler ==========

class CommandHandler:
    """斜杠命令路由和执行器"""

    def __init__(self, handler: "ChatHandler"):
        self._h = handler  # ChatHandler 实例引用

    async def handle(self, cmd: str, user_id: str, persona_name: str):
        """处理一条斜杠命令，返回 True=已处理 / False=不是命令 / "quit"=退出"""
        cmd = cmd.strip().lower()

        if cmd == "/help":
            self._cmd_help()
            return True

        if cmd.startswith("/stats"):
            await self._cmd_stats(cmd, user_id)
            return True

        if cmd.startswith("/memories"):
            parts = cmd.split(maxsplit=1)
            sub = parts[1].strip() if len(parts) > 1 else "list"
            await self._cmd_memories(user_id, sub)
            return True

        if cmd in ("/persona", "/personality") or cmd.startswith("/persona ") or cmd.startswith("/personality "):
            if cmd.startswith("/personality"):
                self._cmd_personality(user_id)
                return True
            parts = cmd.split(maxsplit=1)
            sub = parts[1].strip() if len(parts) > 1 else ""
            self._cmd_persona(user_id, sub)
            return True

        if cmd == "/clear" or cmd == "/clear --confirm":
            self._cmd_clear(user_id, cmd)
            return True

        if cmd == "/debug":
            self._cmd_debug()
            return True

        if cmd.startswith("/export"):
            parts = cmd.split(maxsplit=1)
            fmt = parts[1].strip() if len(parts) > 1 else "md"
            await self._cmd_export(user_id, fmt)
            return True

        if cmd == "/undo":
            self._cmd_undo(user_id)
            return True

        if cmd == "/regen":
            await self._cmd_regen(user_id, persona_name)
            return True

        if cmd.startswith("/search"):
            keyword = cmd[8:].strip() if len(cmd) > 7 else ""
            self._cmd_search(user_id, keyword)
            return True

        if cmd == "/mood":
            self._cmd_mood(user_id)
            return True

        if cmd == "/personality":
            self._cmd_personality(user_id)
            return True

        if cmd == "/tools":
            self._cmd_tools()
            return True

        if cmd.startswith("/img"):
            await self._cmd_img(user_id, cmd)
            return True

        if cmd == "/quit":
            return "quit"

        return False

    # ---- 命令实现 ----

    def _cmd_help(self):
        print(f"\n{Colors.YELLOW}📖 可用命令：{Colors.RESET}")
        for name, desc in COMMANDS.items():
            print(f"  {Colors.CYAN}{name}{Colors.RESET} — {desc}")
        print()

    async def _cmd_stats(self, cmd: str, user_id: str):
        parts = cmd.split(maxsplit=1)
        sub = parts[1].strip() if len(parts) > 1 else ""

        if sub == "dashboard":
            msgs = self._h.chat_history.get_messages(user_id)
            stats = ChatStats(msgs)
            print(f"\n{Colors.YELLOW}{format_dashboard(stats)}{Colors.RESET}\n")
            return

        rel_stats = self._h._affection_storage.get_stats(
            user_id, persona_id=self._h.current_persona_id
        )
        days = rel_stats.days_known
        level = int(rel_stats.level)
        msgs = rel_stats.message_count
        pos = rel_stats.positive_count
        neg = rel_stats.negative_count

        relation = (
            "💕 恋人" if level >= 80 else
            "💗 亲密" if level >= 60 else
            "💛 朋友" if level >= 40 else
            "🤍 熟悉" if level >= 20 else
            "⬜ 陌生"
        )

        print(f"\n{Colors.YELLOW}💕 亲密度统计{Colors.RESET}")
        print(f"  等级：{relation}（{level}/100）")
        print(f"  消息：{msgs} 条（👍 {pos} / 👎 {neg}）")
        print(f"  认识：{days} 天")

        # 最近情感理解（从最近用户消息中提取）
        msgs_list = self._h.chat_history.get_messages(user_id)
        for m in reversed(msgs_list):
            if m["role"] == "user" and "emotion_understanding" in m:
                snippet = m["emotion_understanding"]
                if snippet:
                    print(f"  最近情感：{snippet}")
                break

        print(f"\n  {Colors.DIM}仪表盘：/stats dashboard{Colors.RESET}")
        print()

    # ---- 记忆命令子处理器 ----

    def _mem_help(self, _user_id: str, _parts: list[str]) -> None:
        print(f"\n{Colors.YELLOW}🧠 记忆管理：{Colors.RESET}")
        print(f"  {Colors.CYAN}/memories list [page]{Colors.RESET} — 查看全部记忆（分页）")
        print(f"  {Colors.CYAN}/memories search <关键词>{Colors.RESET} — 搜索记忆")
        print(f"  {Colors.CYAN}/memories add <内容> [等级]{Colors.RESET} — 手动添加记忆（等级 1-5）")
        print(f"  {Colors.CYAN}/memories delete <id>{Colors.RESET} — 删除指定记忆")
        print(f"  {Colors.CYAN}/memories export{Colors.RESET} — 导出所有记忆到 JSON 文件")
        print(f"  {Colors.CYAN}/memories clear --confirm{Colors.RESET} — 清空全部记忆（需确认）")
        print()

    def _mem_list(self, user_id: str, parts: list[str]) -> None:
        page = int(parts[1].strip()) if len(parts) > 1 and parts[1].strip().isdigit() else 1
        per_page = 10
        offset = (page - 1) * per_page
        memories, total = self._h.memory_mgr.list_all_memories(
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

    def _mem_search(self, user_id: str, parts: list[str]) -> None:
        keyword = parts[1].strip() if len(parts) > 1 else ""
        if not keyword:
            print(f"\n{Colors.DIM}  用法：/memories search <关键词>{Colors.RESET}\n")
            return
        results = self._h.memory_mgr.search_memories(user_id, keyword)
        if not results:
            print(f"\n{Colors.DIM}  未找到包含「{keyword}」的记忆{Colors.RESET}\n")
        else:
            print(f"\n{Colors.YELLOW}🔍 搜索「{keyword}」找到 {len(results)} 条记忆：{Colors.RESET}")
            for m in results:
                stars = "⭐" * m.level
                print(f"  {Colors.CYAN}{m.id}{Colors.RESET} {stars} {m.content[:60]}")
            print()

    def _mem_add(self, user_id: str, parts: list[str]) -> None:
        if len(parts) < 2 or not parts[1].strip():
            print(f"\n{Colors.DIM}  用法：/memories add <内容> [等级1-5]{Colors.RESET}\n")
            return
        add_parts = parts[1].strip().rsplit(maxsplit=1)
        content = add_parts[0]
        level = None
        if len(add_parts) > 1 and add_parts[1].isdigit():
            level = max(1, min(5, int(add_parts[1])))
        mem = self._h.memory_mgr.add_memory_sync(user_id, content, level=level)
        if mem:
            print(f"\n{Colors.GREEN}✅ 已添加记忆 {mem.id}（等级 {mem.level}）：{mem.content[:40]}{Colors.RESET}\n")
        else:
            print(f"\n{Colors.DIM}  记忆内容太简单，没有记住~（评分 < 2）{Colors.RESET}\n")

    def _mem_delete(self, user_id: str, parts: list[str]) -> None:
        if len(parts) < 2 or not parts[1].strip():
            print(f"\n{Colors.DIM}  用法：/memories delete <记忆id>{Colors.RESET}\n")
            return
        mid = parts[1].strip()
        if self._h.memory_mgr.delete_memory(user_id, mid):
            print(f"\n{Colors.GREEN}✅ 已删除记忆 {mid}{Colors.RESET}\n")
        else:
            print(f"\n{Colors.DIM}  未找到记忆 {mid}{Colors.RESET}\n")

    def _mem_export(self, user_id: str, _parts: list[str]) -> None:
        all_ms = self._h.memory_mgr.export_memories(user_id)
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
        export_path = Path(self._h.memory_mgr.data_dir) / f"memories_{user_id}.json"
        with open(export_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"\n{Colors.GREEN}✅ 已导出 {len(all_ms)} 条记忆到 {export_path}{Colors.RESET}\n")

    def _mem_clear(self, user_id: str, parts: list[str]) -> None:
        all_ms = self._h.memory_mgr.export_memories(user_id)
        if not all_ms:
            print(f"\n{Colors.DIM}  已经没有记忆了~{Colors.RESET}\n")
            return
        rest = parts[1].strip() if len(parts) > 1 else ""
        if "--confirm" not in rest:
            print(f"\n{Colors.YELLOW}⚠ 这会清空全部 {len(all_ms)} 条记忆，无法恢复{Colors.RESET}")
            print(f"  {Colors.DIM}输入 /memories clear --confirm 确认清空{Colors.RESET}")
            print(f"  {Colors.DIM}输入 /memories export 先备份记忆{Colors.RESET}\n")
            return
        storage = MemoryStorage(str(self._h.memory_mgr.data_dir))
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

    async def _cmd_memories(self, user_id: str, sub: str):
        parts = sub.split(maxsplit=1)
        action = parts[0] if parts else "list"

        handler = self._MEMORY_DISPATCH.get(action)
        if handler:
            handler(self, user_id, parts)
        else:
            print(f"\n{Colors.DIM}  未知操作：{action}，输入 /memories help 查看帮助{Colors.RESET}\n")

    def _cmd_persona(self, user_id: str, sub: str):
        parts = sub.split(maxsplit=1) if sub else []

        if sub == "list":
            all_p = self._h.persona_loader.list_all()
            if not all_p:
                print(f"\n{Colors.DIM}  没有可用的人设{Colors.RESET}\n")
                return
            print(f"\n{Colors.YELLOW}🎀 人设列表：{Colors.RESET}")
            for p in all_p:
                marker = f" {Colors.GREEN}<- 当前{Colors.RESET}" if p.id == self._h.current_persona_id else ""
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
            target = self._h.persona_loader.get(target_id)
            if not target:
                print(f"\n{Colors.DIM}  未找到人设 {target_id}{Colors.RESET}\n")
                return
            if target_id == self._h.current_persona_id:
                print(f"\n{Colors.DIM}  已经在使用 {target.name} 了~{Colors.RESET}\n")
                return
            self._h.current_persona_id = target_id
            print(f"\n{Colors.GREEN}✅ 已切换到 {target.name}（{target.id}）{Colors.RESET}")
            level = int(self._h._affection_storage.get_level(
                user_id, persona_id=target_id
            ))
            print(f"  {Colors.DIM}💕 与 {target.name} 的亲密度：{level}/100{Colors.RESET}\n")
            return

        # 默认显示当前人设详情
        p = self._h.persona_loader.get(self._h.current_persona_id)
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

    def _cmd_clear(self, user_id: str, cmd: str):
        if cmd == "/clear":
            msgs = self._h.chat_history.get_messages(user_id)
            count = len(msgs)
            print(f"\n{Colors.YELLOW}⚠ 这会清空所有聊天历史（{count} 条消息），无法恢复{Colors.RESET}")
            print(f"  {Colors.DIM}输入 /clear --confirm 确认清空，或 /export 先备份{Colors.RESET}\n")
            return
        self._h.chat_history.delete_user(user_id)
        print(f"\n{Colors.GREEN}✅ 聊天历史已清空{Colors.RESET}\n")

    def _cmd_debug(self):
        prompt = self._h.pipeline.get_last_system_prompt()
        if prompt:
            print(f"\n{Colors.YELLOW}🔧 当前 System Prompt：{Colors.RESET}")
            print(f"{Colors.DIM}{'─' * 50}{Colors.RESET}")
            for line in prompt.split("\n"):
                print(f"  {line}")
            print(f"{Colors.DIM}{'─' * 50}{Colors.RESET}")
            print(f"  {Colors.DIM}共 {len(prompt)} 字符{Colors.RESET}\n")
        else:
            print(f"\n{Colors.DIM}  还没有发送过消息，没有 system prompt 可查看{Colors.RESET}\n")

    async def _cmd_export(self, user_id: str, fmt: str):
        msgs = self._h.chat_history.get_messages(user_id)
        if not msgs:
            print(f"\n{Colors.DIM}  没有可导出的聊天记录{Colors.RESET}\n")
            return

        persona = self._h.persona_loader.get(self._h.current_persona_id)
        persona_name = persona.name if persona else "AI"
        export_dir = Path(self._h.chat_history.data_dir) / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)

        if fmt == "json":
            filename = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = export_dir / filename
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(msgs, f, ensure_ascii=False, indent=2)
        else:
            filename = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            filepath = export_dir / filename
            md_content = self._h.chat_history.export_markdown(user_id, persona_name)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(md_content)

        print(f"\n{Colors.GREEN}✅ 已导出到 {filepath}{Colors.RESET}")
        print(f"  {Colors.DIM}格式：{'Markdown' if fmt != 'json' else 'JSON'}（用 /export json 或 /export md 切换）{Colors.RESET}\n")

    def _cmd_undo(self, user_id: str):
        msgs = self._h.chat_history.get_messages(user_id)
        if len(msgs) < 2:
            print(f"\n{Colors.DIM}  没有可以撤销的消息{Colors.RESET}\n")
            return
        if msgs[-1]["role"] != "assistant" or msgs[-2]["role"] != "user":
            print(f"\n{Colors.YELLOW}⚠ 最后两条消息不是完整的对话轮次，跳过{Colors.RESET}\n")
            return
        deleted = self._h.chat_history.delete_last_messages(user_id, 2)
        print(f"\n{Colors.GREEN}✅ 已撤销最后 {len(deleted)} 条消息{Colors.RESET}")
        for msg in deleted:
            role = "🧑" if msg["role"] == "user" else "💕"
            preview = msg["content"][:40] + ("..." if len(msg["content"]) > 40 else "")
            print(f"  {Colors.DIM}{role} {preview}{Colors.RESET}")
        print()

    async def _cmd_regen(self, user_id: str, persona_name: str):
        msgs = self._h.chat_history.get_messages(user_id)
        if not msgs:
            print(f"\n{Colors.DIM}  还没有对话记录{Colors.RESET}\n")
            return
        if msgs[-1]["role"] != "assistant":
            print(f"\n{Colors.YELLOW}⚠ 最后一条消息不是 AI 回复，无法重新生成{Colors.RESET}\n")
            return

        self._h.chat_history.delete_last_messages(user_id, 1)
        user_msgs = [m for m in msgs if m["role"] == "user"]
        if not user_msgs:
            print(f"\n{Colors.YELLOW}⚠ 找不到对应的用户消息{Colors.RESET}\n")
            return

        last_user = user_msgs[-1]["content"]
        print(f"\n  {Colors.DIM}🔄 重新生成中...{Colors.RESET}")

        reply, rel_level = await self._h.pipeline.process(
            user_id, last_user, self._h.current_persona_id, skip_user_message=True,
        )
        p = self._h.persona_loader.get(self._h.current_persona_id)
        name = p.name if p else persona_name
        print(f"\r  {name}: {reply}\n")

    def _cmd_search(self, user_id: str, keyword: str):
        if not keyword:
            print(f"\n{Colors.YELLOW}用法：/search <关键词>{Colors.RESET}")
            print(f"  {Colors.DIM}示例：/search 生日{Colors.RESET}\n")
            return
        results = self._h.chat_history.search_messages(user_id, keyword)
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

    def _cmd_mood(self, user_id: str):
        msgs = self._h.chat_history.get_messages(user_id)
        user_msgs = [m for m in msgs if m["role"] == "user" and "emotion" in m]
        total = len(user_msgs)

        print(f"\n{Colors.YELLOW}🎭 情绪状态{Colors.RESET}")

        # Mood 引擎数据（新增）
        mood_engine = getattr(self._h, '_mood_engine', None)
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

    def _cmd_personality(self, user_id: str):
        pe = getattr(self._h, '_personality_engine', None)
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

    def _cmd_tools(self):
        tr = getattr(self._h, '_tool_registry', None)
        if not tr or not tr.available:
            print(f"\n{Colors.DIM}  没有可用工具{Colors.RESET}\n")
            return
        print(f"\n{Colors.YELLOW}🛠️ 可用工具{Colors.RESET}")
        for tool in tr.list_tools():
            params = tool.parameters
            props = params.get("properties", {})
            param_str = ", ".join(props.keys()) if props else "无参数"
            print(f"  {Colors.CYAN}{tool.name}{Colors.RESET} — {tool.description}")
            print(f"    参数：{param_str}")
        print()

    async def _cmd_img(self, user_id: str, cmd: str):
        """处理 /img 命令：发送图片给 AI 识别"""
        # 保证 ChatHandler 上有 ImageHandler
        img_handler = ImageHandler()
        image_path, user_text = img_handler.parse_img_command(cmd)
        if not image_path:
            print(f"\n{Colors.YELLOW}📷 发送图片：{Colors.RESET}")
            print(f"  {Colors.CYAN}/img <图片路径> [文字说明]{Colors.RESET}")
            print(f"  {Colors.DIM}示例：/img C:\\photo.jpg 看看这个{Colors.RESET}")
            print(f"  {Colors.DIM}支持 jpg/png/gif/webp/bmp，最大 10MB{Colors.RESET}\n")
            return

        # 加载图片
        loaded = img_handler.load_image(image_path)
        if not loaded:
            print(f"\n{Colors.DIM}  图片加载失败：{image_path}{Colors.RESET}\n")
            return

        b64_data, mime_type = loaded
        print(f"\n{Colors.YELLOW}📷 正在识别图片...{Colors.RESET}")

        # 构建 vision 消息
        vision_messages = img_handler.build_vision_messages(b64_data, mime_type, user_text)
        vision_prompt = img_handler.get_vision_prompt()

        # 通过 LLM 识别
        llm = getattr(self._h, '_registry', None)
        if llm and llm.available_models:
            model = llm.get()
            try:
                # 使用标准 chat（非流式）返回图片描述
                response = await model.chat(
                    messages=vision_messages,
                    system_prompt=vision_prompt,
                )
                reply = response.content
                # 情感增强
                mood_for_img = None
                if self._h._mood_engine:
                    mood_for_img = self._h._mood_engine.get_mood(user_id)
                from core.emotion import EmotionEnhancer
                reply = EmotionEnhancer.enhance_reply(reply, mood_state=mood_for_img)
                # 保存到聊天历史
                self._h.chat_history.add_message(
                    user_id, "user",
                    f"[图片] {user_text}" if user_text else "[图片]",
                )
                self._h.chat_history.add_message(user_id, "assistant", reply)
                persona = self._h.persona_loader.get(self._h.current_persona_id)
                p_name = persona.name if persona else "AI"
                print(f"\n{Colors.MAGENTA}{p_name}:{Colors.RESET} {reply}\n")
            except Exception as e:
                logger.error(f"图片识别失败: {e}")
                print(f"\n{Colors.DIM}  图片识别失败，模型不支持 vision 功能{Colors.RESET}\n")
        else:
            print(f"\n{Colors.DIM}  没有可用的模型{Colors.RESET}\n")
