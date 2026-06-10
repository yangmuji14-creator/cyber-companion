"""Cyber Girlfriend - 赛博女友（纯 CMD 聊天）

运行方式：
    python main.py setup   — 首次运行设置向导
    python main.py         — 直接进聊天
"""

import asyncio
import json
import os
import sys
import threading
import queue
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
from loguru import logger

load_dotenv()

ROOT = Path(__file__).parent
CONFIG_DIR = ROOT / "config"

# 日志
logger.remove()
logger.add(sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{level:8}</level> | {message}")
logger.add("logs/app.log", rotation="10 MB", retention="7 days", level="DEBUG")


# ========== ANSI 颜色 ==========
class Colors:
    """ANSI 颜色码（Windows 10+ 原生支持）"""
    CYAN = "\033[36m"      # 用户消息
    MAGENTA = "\033[35m"   # AI 回复
    YELLOW = "\033[33m"    # 系统消息
    GREEN = "\033[32m"     # 成功
    RED = "\033[31m"       # 错误
    DIM = "\033[2m"        # 暗淡（时间戳）
    BOLD = "\033[1m"       # 加粗
    RESET = "\033[0m"      # 重置


# ========== 加载配置 ==========
def _load_advanced() -> dict:
    """从 settings.json 读取高级参数"""
    path = CONFIG_DIR / "settings.json"
    defaults = {
        "segment_max_length": 50,
        "debounce_seconds": 3,
        "summarize_threshold": 15,
        "max_retries": 2,
        "max_messages": 50,
        "proactive_enabled": True,
        "proactive_morning": True,
        "proactive_evening": True,
        "proactive_missing_days": 2,
        "proactive_min_level": 20,
    }
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            advanced = data.get("advanced", {})
            defaults.update({k: v for k, v in advanced.items() if k in defaults})
        except Exception:
            pass
    return defaults


ADVANCED = _load_advanced()


# ========== 核心组件 ==========
from core.llm import init_registry
from core.memory import MemoryManager, MemorySummarizer, ChatHistoryStorage
from core.memory.stats import ChatStats, format_dashboard
from core.persona import PersonaLoader, PromptBuilder
from core.emotion import EmotionAnalyzer, EmotionEnhancer, MessageSegmenter, LLMEmotionAnalyzer
from core.relationship import RelationshipTracker
from core.proactive import ProactiveMessenger

registry = init_registry(CONFIG_DIR / "settings.json")
memory_mgr = MemoryManager(str(ROOT / "data"))
persona_loader = PersonaLoader(CONFIG_DIR / "personas.json")
emotion_analyzer = EmotionAnalyzer()  # 关键词分析（快速）
llm_emotion_analyzer = LLMEmotionAnalyzer()  # LLM 辅助（会在首次对话时初始化）
relationship_tracker = RelationshipTracker(str(ROOT / "data"))
chat_history = ChatHistoryStorage(str(ROOT / "data"), max_messages=ADVANCED["max_messages"])
proactive = ProactiveMessenger(
    persona_loader, memory_mgr, relationship_tracker,
    config=ADVANCED,
)

# 后台任务集合（防止 asyncio.create_task 的 task 被 GC）
_background_tasks: set = set()


# ========== 会话统计 ==========
class SessionStats:
    """本次会话统计"""

    def __init__(self):
        self.message_count = 0
        self.memories_added = 0
        self.start_level = 0
        self.end_level = 0
        self.start_time = datetime.now()

    def summary(self, persona_name: str) -> str:
        """生成会话总结"""
        elapsed = (datetime.now() - self.start_time).total_seconds()
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)

        level_change = self.end_level - self.start_level
        if level_change > 0:
            level_str = f"{Colors.GREEN}+{level_change}{Colors.RESET}"
        elif level_change < 0:
            level_str = f"{Colors.RED}{level_change}{Colors.RESET}"
        else:
            level_str = "无变化"

        lines = [
            "",
            f"{Colors.YELLOW}{'=' * 40}{Colors.RESET}",
            f"{Colors.BOLD}📊 会话总结{Colors.RESET}",
            f"  ⏱  时长：{minutes}分{seconds}秒",
            f"  💬 消息：{self.message_count} 条",
            f"  🧠 新增记忆：{self.memories_added} 条",
            f"  💕 亲密度：{self.start_level} → {self.end_level}（{level_str}）",
            f"{Colors.YELLOW}{'=' * 40}{Colors.RESET}",
            f"{Colors.DIM}{persona_name}: 下次见啦~{Colors.RESET}",
        ]
        return "\n".join(lines)


# ========== 工具函数 ==========
def _format_multi_message(content: str) -> tuple[str, int]:
    """格式化多条合并消息

    Returns:
        (formatted_content, message_count) 元组
    """
    lines = [line.strip() for line in content.split("\n") if line.strip()]
    if len(lines) <= 1:
        return content, 1

    # 多条消息：格式化为清晰的列表
    formatted_parts = []
    for i, line in enumerate(lines, 1):
        formatted_parts.append(f"[消息{i}] {line}")

    return "\n".join(formatted_parts), len(lines)


def _get_time_context() -> str:
    now = datetime.now()
    hour = now.hour
    if 0 <= hour < 6:
        period = "深夜"
    elif 6 <= hour < 9:
        period = "早上"
    elif 9 <= hour < 12:
        period = "上午"
    elif 12 <= hour < 14:
        period = "中午"
    elif 14 <= hour < 18:
        period = "下午"
    elif 18 <= hour < 22:
        period = "晚上"
    else:
        period = "深夜"
    return f"现在是{period} {now.strftime('%Y-%m-%d %H:%M')}"


def _timestamp() -> str:
    """当前时间 HH:MM"""
    return datetime.now().strftime("%H:%M")


def _get_welcome_message(persona, rel_level: int) -> str:
    """根据时间和亲密度生成欢迎语"""
    hour = datetime.now().hour

    if rel_level >= 80:
        # 恋人关系
        if 0 <= hour < 6:
            return "你怎么这么晚还不睡呀？是不是在想我？哼哼~"
        elif 6 <= hour < 9:
            return "早安早安~ 今天也要元气满满哦！"
        elif 18 <= hour < 22:
            return "你回来啦~ 今天过得怎么样？我好想你！"
        else:
            return "嘿嘿，你来了~ 我一直在等你呢！"
    elif rel_level >= 40:
        # 朋友以上
        if 0 <= hour < 6:
            return "这么晚还没睡呀？注意身体哦~"
        elif 6 <= hour < 9:
            return "早安~ 今天有什么安排吗？"
        elif 18 <= hour < 22:
            return "嗨~ 今天过得怎么样？"
        else:
            return "来啦~ 最近忙吗？"
    else:
        # 刚认识
        if 6 <= hour < 12:
            return "你好呀~ 今天天气不错呢！"
        elif 18 <= hour < 22:
            return "嗨，又见面了~"
        else:
            return "你好呀~"


# ========== 斜杠命令 ==========
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
    "/mood": "查看当前情绪状态",
    "/quit": "退出聊天",
}


async def handle_command(cmd: str, user_id: str, persona_name: str) -> bool:
    """处理斜杠命令

    Returns:
        True 如果命令已处理，False 如果不是命令
    """
    cmd = cmd.strip().lower()

    if cmd == "/help":
        print(f"\n{Colors.YELLOW}📖 可用命令：{Colors.RESET}")
        for name, desc in COMMANDS.items():
            print(f"  {Colors.CYAN}{name}{Colors.RESET} — {desc}")
        print()
        return True

    elif cmd.startswith("/stats"):
        parts = cmd.split(maxsplit=1)
        sub = parts[1].strip() if len(parts) > 1 else ""

        if sub == "dashboard":
            messages = chat_history.get_messages(user_id)
            chat_stats = ChatStats(messages)
            print(f"\n{Colors.YELLOW}{format_dashboard(chat_stats)}{Colors.RESET}\n")
        else:
            rel_stats = relationship_tracker.get_stats(user_id, persona_id=_current_persona_id)
            days = rel_stats.get("days_known", 0)
            level = rel_stats.get("level", 50)
            msgs = rel_stats.get("message_count", 0)
            pos = rel_stats.get("positive_count", 0)
            neg = rel_stats.get("negative_count", 0)

            # 亲密度等级描述
            if level >= 80:
                relation = "💕 恋人"
            elif level >= 60:
                relation = "💗 亲密"
            elif level >= 40:
                relation = "💛 朋友"
            elif level >= 20:
                relation = "🤍 熟悉"
            else:
                relation = "⬜ 陌生"

            print(f"\n{Colors.YELLOW}💕 亲密度统计{Colors.RESET}")
            print(f"  等级：{relation}（{level}/100）")
            print(f"  消息：{msgs} 条（👍 {pos} / 👎 {neg}）")
            print(f"  认识：{days:.0f} 天")
            print(f"\n  {Colors.DIM}仪表盘：/stats dashboard{Colors.RESET}")
            print()
        return True

    elif cmd.startswith("/memories"):
        parts = cmd.split(maxsplit=1)
        sub = parts[1].strip() if len(parts) > 1 else "list"
        await _handle_memories_sub(user_id, sub)
        return True

    elif cmd.startswith("/persona"):
        parts = cmd.split(maxsplit=1)
        sub = parts[1].strip() if len(parts) > 1 else ""
        _handle_persona_sub(user_id, sub)
        return True

    elif cmd == "/clear" or cmd == "/clear --confirm":
        if cmd == "/clear":
            msgs = chat_history.get_messages(user_id)
            count = len(msgs)
            print(f"\n{Colors.YELLOW}⚠ 这会清空所有聊天历史（{count} 条消息），无法恢复{Colors.RESET}")
            print(f"  {Colors.DIM}输入 /clear --confirm 确认清空，或 /export 先备份{Colors.RESET}\n")
            return True
        chat_history.delete_user(user_id)
        print(f"\n{Colors.GREEN}✅ 聊天历史已清空{Colors.RESET}\n")
        return True

    elif cmd == "/debug":
        if _last_system_prompt:
            print(f"\n{Colors.YELLOW}🔧 当前 System Prompt：{Colors.RESET}")
            print(f"{Colors.DIM}{'─' * 50}{Colors.RESET}")
            for line in _last_system_prompt.split("\n"):
                print(f"  {line}")
            print(f"{Colors.DIM}{'─' * 50}{Colors.RESET}")
            print(f"  {Colors.DIM}共 {len(_last_system_prompt)} 字符{Colors.RESET}\n")
        else:
            print(f"\n{Colors.DIM}  还没有发送过消息，没有 system prompt 可查看{Colors.RESET}\n")
        return True

    elif cmd.startswith("/export"):
        parts = cmd.split(maxsplit=1)
        fmt = parts[1].strip() if len(parts) > 1 else "md"

        messages = chat_history.get_messages(user_id)
        if not messages:
            print(f"\n{Colors.DIM}  没有可导出的聊天记录{Colors.RESET}\n")
            return True

        export_dir = ROOT / "data" / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)

        if fmt == "json":
            filename = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = export_dir / filename
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(messages, f, ensure_ascii=False, indent=2)
        else:
            # 默认 Markdown 格式
            filename = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            filepath = export_dir / filename
            persona = persona_loader.get(_current_persona_id)
            persona_name = persona.name if persona else "AI"
            md_content = chat_history.export_markdown(user_id, persona_name)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(md_content)

        print(f"\n{Colors.GREEN}✅ 已导出到 {filepath}{Colors.RESET}")
        print(f"  {Colors.DIM}格式：{'Markdown' if fmt != 'json' else 'JSON'}（用 /export json 或 /export md 切换）{Colors.RESET}\n")
        return True

    elif cmd == "/undo":
        messages = chat_history.get_messages(user_id)
        if len(messages) < 2:
            print(f"\n{Colors.DIM}  没有可以撤销的消息{Colors.RESET}\n")
        else:
            # 确认最后两条是 user + assistant
            if messages[-1]["role"] != "assistant" or messages[-2]["role"] != "user":
                print(f"\n{Colors.YELLOW}⚠ 最后两条消息不是完整的对话轮次，跳过{Colors.RESET}\n")
            else:
                deleted = chat_history.delete_last_messages(user_id, 2)
                print(f"\n{Colors.GREEN}✅ 已撤销最后 {len(deleted)} 条消息{Colors.RESET}")
                # 显示被撤销的消息摘要
                for msg in deleted:
                    role = "🧑" if msg["role"] == "user" else "💕"
                    preview = msg["content"][:40] + ("..." if len(msg["content"]) > 40 else "")
                    print(f"  {Colors.DIM}{role} {preview}{Colors.RESET}")
                print()
        return True

    elif cmd == "/regen":
        await _handle_regen(user_id, persona_name)
        return True

    elif cmd.startswith("/search"):
        keyword = cmd[8:].strip() if len(cmd) > 7 else ""
        if not keyword:
            print(f"\n{Colors.YELLOW}用法：/search <关键词>{Colors.RESET}")
            print(f"  {Colors.DIM}示例：/search 生日{Colors.RESET}\n")
        else:
            results = chat_history.search_messages(user_id, keyword)
            if not results:
                print(f"\n{Colors.DIM}  未找到包含「{keyword}」的消息{Colors.RESET}\n")
            else:
                print(f"\n{Colors.YELLOW}🔍 搜索「{keyword}」找到 {len(results)} 条结果：{Colors.RESET}")
                for r in results:
                    idx = r["index"]
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

                    # 上下文
                    if before:
                        b_role = "🧑" if before["role"] == "user" else "💕"
                        b_preview = before["content"][:30] + ("..." if len(before["content"]) > 30 else "")
                        print(f"  {Colors.DIM}{b_role} {b_preview}{Colors.RESET}")

                    # 匹配消息（高亮关键词）
                    content = msg["content"]
                    highlighted = content.replace(keyword, f"{Colors.YELLOW}{keyword}{Colors.RESET}")
                    print(f"  {Colors.CYAN}[#{idx}]{Colors.RESET} {role_icon}{time_str} {highlighted}")

                    if after:
                        a_role = "🧑" if after["role"] == "user" else "💕"
                        a_preview = after["content"][:30] + ("..." if len(after["content"]) > 30 else "")
                        print(f"  {Colors.DIM}{a_role} {a_preview}{Colors.RESET}")
                    print()
        return True

    elif cmd == "/mood":
        messages = chat_history.get_messages(user_id)
        user_msgs = [m for m in messages if m["role"] == "user" and "emotion" in m]
        if not user_msgs:
            print(f"\n{Colors.DIM}  还没有足够的情绪数据{Colors.RESET}\n")
        else:
            # 统计情绪分布
            from collections import Counter
            emotions = Counter(m["emotion"] for m in user_msgs)
            total = len(user_msgs)

            # 情绪 emoji 映射
            emotion_icons = {
                "happy": "😊", "sad": "😢", "angry": "😠", "neutral": "😐",
                "excited": "🤩", "lonely": "🥺", "anxious": "😰", "love": "😍",
            }

            # 最近一条情绪
            latest = user_msgs[-1]
            latest_emoji = emotion_icons.get(latest["emotion"], "❓")
            latest_intensity = latest.get("emotion_intensity", 0)

            print(f"\n{Colors.YELLOW}🎭 情绪状态{Colors.RESET}")
            print(f"  当前：{latest_emoji} {latest['emotion']}（强度 {latest_intensity:.0%}）")
            print(f"  {Colors.DIM}基于最近 {total} 条消息{Colors.RESET}")
            print()

            # 分布条形图
            print(f"  {Colors.CYAN}情绪分布：{Colors.RESET}")
            for emotion, count in emotions.most_common():
                icon = emotion_icons.get(emotion, "❓")
                pct = count / total * 100
                bar_len = int(pct / 5)
                bar = "█" * bar_len + "░" * (20 - bar_len)
                print(f"  {icon} {emotion:8s} {bar} {count}次 ({pct:.0f}%)")
            print()
        return True

    elif cmd == "/quit":
        return "quit"

    return False


# ========== 人设子命令 ==========
_current_persona_id = "girlfriend_001"


def _handle_persona_sub(user_id: str, sub: str):
    """处理 /persona 子命令"""
    global _current_persona_id

    parts = sub.split(maxsplit=1)

    if sub == "list":
        all_personas = persona_loader.list_all()
        if not all_personas:
            print(f"\n{Colors.DIM}  没有可用的人设{Colors.RESET}\n")
            return
        print(f"\n{Colors.YELLOW}🎀 人设列表：{Colors.RESET}")
        for p in all_personas:
            marker = f" {Colors.GREEN}← 当前{Colors.RESET}" if p.id == _current_persona_id else ""
            mbti = f" [{p.mbti}]" if p.mbti else ""
            traits = f" {'、'.join(p.personality[:3])}" if p.personality else ""
            print(f"  {Colors.CYAN}{p.id}{Colors.RESET} — {p.name}（{p.age}岁{mbti}）{traits}{marker}")
        print(f"\n  {Colors.DIM}切换：/persona switch <id>{Colors.RESET}\n")

    elif parts[0] == "switch":
        if len(parts) < 2 or not parts[1]:
            print(f"\n{Colors.DIM}  用法：/persona switch <id>{Colors.RESET}\n")
            return
        target_id = parts[1].strip()
        target = persona_loader.get(target_id)
        if not target:
            print(f"\n{Colors.DIM}  未找到人设 {target_id}{Colors.RESET}\n")
            return
        if target_id == _current_persona_id:
            print(f"\n{Colors.DIM}  已经在使用 {target.name} 了~{Colors.RESET}\n")
            return
        _current_persona_id = target_id
        print(f"\n{Colors.GREEN}✅ 已切换到 {target.name}（{target.id}）{Colors.RESET}")
        # 显示新角色的亲密度
        level = relationship_tracker.get_level(user_id, base_level=target.relationship_level, persona_id=target_id)
        print(f"  {Colors.DIM}💕 与 {target.name} 的亲密度：{level}/100{Colors.RESET}\n")

    else:
        # 默认显示当前人设详情
        persona = persona_loader.get(_current_persona_id)
        if persona:
            print(f"\n{Colors.YELLOW}🎀 人设信息{Colors.RESET}")
            print(f"  名字：{persona.name}")
            print(f"  年龄：{persona.age}岁")
            if persona.personality:
                print(f"  性格：{'、'.join(persona.personality)}")
            if persona.hobbies:
                hobbies = [h.get("name", "") for h in persona.hobbies[:3]]
                print(f"  爱好：{'、'.join(hobbies)}")
            if persona.catchphrases:
                print(f"  口头禅：{'、'.join(persona.catchphrases)}")
            print(f"\n  {Colors.DIM}人设列表：/persona list | 切换：/persona switch <id>{Colors.RESET}\n")


# ========== /regen 处理 ==========
async def _handle_regen(user_id: str, persona_name: str):
    """重新生成上一条 AI 回复"""
    messages = chat_history.get_messages(user_id)
    if not messages:
        print(f"\n{Colors.DIM}  还没有对话记录{Colors.RESET}\n")
        return

    if messages[-1]["role"] != "assistant":
        print(f"\n{Colors.YELLOW}⚠ 最后一条消息不是 AI 回复，无法重新生成{Colors.RESET}\n")
        return

    # 删除最后一条 assistant 消息
    chat_history.delete_last_messages(user_id, 1)

    # 找到最后一条 user 消息的 content
    user_msgs = [m for m in messages if m["role"] == "user"]
    if not user_msgs:
        print(f"\n{Colors.YELLOW}⚠ 找不到对应的用户消息{Colors.RESET}\n")
        return

    last_user_content = user_msgs[-1]["content"]
    print(f"\n  {Colors.DIM}🔄 重新生成中...{Colors.RESET}")

    # 重新调用 handle_message，跳过用户消息存储
    reply, rel_level = await handle_message(
        user_id, last_user_content,
        skip_user_message=True,
    )

    # 流式显示新回复
    persona = persona_loader.get(_current_persona_id)
    name = persona.name if persona else persona_name
    print(f"\r  {name}: {reply}\n")


# ========== 记忆子命令 ==========
async def _handle_memories_sub(user_id: str, sub: str):
    """处理 /memories 子命令"""
    parts = sub.split(maxsplit=1)
    action = parts[0] if parts else "list"

    if action == "help":
        print(f"\n{Colors.YELLOW}🧠 记忆管理：{Colors.RESET}")
        print(f"  {Colors.CYAN}/memories list [page]{Colors.RESET} — 查看全部记忆（分页）")
        print(f"  {Colors.CYAN}/memories search <关键词>{Colors.RESET} — 搜索记忆")
        print(f"  {Colors.CYAN}/memories add <内容> [等级]{Colors.RESET} — 手动添加记忆（等级 1-5）")
        print(f"  {Colors.CYAN}/memories delete <id>{Colors.RESET} — 删除指定记忆")
        print(f"  {Colors.CYAN}/memories export{Colors.RESET} — 导出所有记忆到 JSON 文件")
        print(f"  {Colors.CYAN}/memories clear --confirm{Colors.RESET} — 清空全部记忆（需确认）")
        print()

    elif action == "list":
        page = int(parts[1].strip()) if len(parts) > 1 and parts[1].strip().isdigit() else 1
        per_page = 10
        offset = (page - 1) * per_page
        memories, total = memory_mgr.list_all_memories(user_id, offset=offset, limit=per_page)
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

    elif action == "search":
        keyword = parts[1].strip() if len(parts) > 1 else ""
        if not keyword:
            print(f"\n{Colors.DIM}  用法：/memories search <关键词>{Colors.RESET}\n")
            return
        results = memory_mgr.search_memories(user_id, keyword)
        if not results:
            print(f"\n{Colors.DIM}  未找到包含「{keyword}」的记忆{Colors.RESET}\n")
        else:
            print(f"\n{Colors.YELLOW}🔍 搜索「{keyword}」找到 {len(results)} 条记忆：{Colors.RESET}")
            for m in results:
                stars = "⭐" * m.level
                print(f"  {Colors.CYAN}{m.id}{Colors.RESET} {stars} {m.content[:60]}")
            print()

    elif action == "add":
        if len(parts) < 2 or not parts[1].strip():
            print(f"\n{Colors.DIM}  用法：/memories add <内容> [等级1-5]{Colors.RESET}\n")
            return
        add_parts = parts[1].strip().rsplit(maxsplit=1)
        content = add_parts[0]
        level = None
        if len(add_parts) > 1 and add_parts[1].isdigit():
            level = max(1, min(5, int(add_parts[1])))
        memory = memory_mgr.add_memory(user_id, content, level=level)
        if memory:
            print(f"\n{Colors.GREEN}✅ 已添加记忆 {memory.id}（等级 {memory.level}）：{memory.content[:40]}{Colors.RESET}\n")
        else:
            print(f"\n{Colors.DIM}  记忆内容太简单，没有记住~（评分 < 2）{Colors.RESET}\n")

    elif action == "delete":
        if len(parts) < 2 or not parts[1].strip():
            print(f"\n{Colors.DIM}  用法：/memories delete <记忆id>{Colors.RESET}\n")
            return
        memory_id = parts[1].strip()
        if memory_mgr.delete_memory(user_id, memory_id):
            print(f"\n{Colors.GREEN}✅ 已删除记忆 {memory_id}{Colors.RESET}\n")
        else:
            print(f"\n{Colors.DIM}  未找到记忆 {memory_id}{Colors.RESET}\n")

    elif action == "export":
        all_memories = memory_mgr.export_memories(user_id)
        if not all_memories:
            print(f"\n{Colors.DIM}  还没有记忆可以导出~{Colors.RESET}\n")
            return
        export_data = {
            "user_id": user_id,
            "count": len(all_memories),
            "memories": [
                {
                    "id": m.id,
                    "content": m.content,
                    "level": m.level,
                    "tags": m.tags,
                    "created_at": m.created_at,
                }
                for m in all_memories
            ],
        }
        export_path = ROOT / "data" / f"memories_{user_id}.json"
        import json
        with open(export_path, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        print(f"\n{Colors.GREEN}✅ 已导出 {len(all_memories)} 条记忆到 {export_path}{Colors.RESET}\n")

    elif action == "clear":
        all_memories = memory_mgr.export_memories(user_id)
        if not all_memories:
            print(f"\n{Colors.DIM}  已经没有记忆了~{Colors.RESET}\n")
            return
        # 检查 --confirm 参数
        rest = parts[1].strip() if len(parts) > 1 else ""
        if "--confirm" not in rest:
            print(f"\n{Colors.YELLOW}⚠ 这会清空全部 {len(all_memories)} 条记忆，无法恢复{Colors.RESET}")
            print(f"  {Colors.DIM}输入 /memories clear --confirm 确认清空{Colors.RESET}")
            print(f"  {Colors.DIM}输入 /memories export 先备份记忆{Colors.RESET}\n")
            return
        # 清空：直接用 storage 删除全部
        from core.memory.storage import MemoryStorage
        storage = MemoryStorage(str(ROOT / "data"))
        storage.delete_all(user_id)
        print(f"\n{Colors.GREEN}✅ 已清空全部 {len(all_memories)} 条记忆{Colors.RESET}\n")

    else:
        print(f"\n{Colors.DIM}  未知操作：{action}，输入 /memories help 查看帮助{Colors.RESET}\n")


# ========== 消息处理 ==========
# 存储最后一次构建的 system prompt，供 /debug 命令查看
_last_system_prompt: str = ""


async def handle_message(
    user_id: str,
    content: str,
    persona_id: str = "",
    on_token: Callable[[str], None] | None = None,
    skip_user_message: bool = False,
) -> tuple[str, int]:
    """统一消息处理逻辑

    Args:
        on_token: 可选的 token 回调，用于流式输出。调用 on_token(token_str) 逐 token 显示。
        skip_user_message: 跳过用户消息存储（用于 /regen 重新生成）

    Returns:
        (reply_text, relationship_level) 元组
    """
    global _last_system_prompt

    if not persona_id:
        persona_id = _current_persona_id

    if not registry.available_models:
        return "我还没配置好模型呢，等等哦~", 50

    llm = registry.get()
    persona = persona_loader.get(persona_id)
    if not persona:
        return "我找不到我的人设了 (´;ω;`)", 50

    # 首次使用时初始化 LLM 情感分析器
    if llm_emotion_analyzer._llm is None:
        llm_emotion_analyzer._llm = llm

    # 格式化多消息：识别是否是多条合并的消息
    formatted_content, msg_count = _format_multi_message(content)

    # 情感分析用原始内容（保留每条消息的情感）— 必须在 add_message 之前
    emotion = await llm_emotion_analyzer.analyze(content)

    # 存储格式化后的消息到聊天历史（含情感数据）
    # /regen 时跳过，因为用户消息已经在历史中
    if not skip_user_message:
        chat_history.add_message(
            user_id, "user", formatted_content,
            emotion=emotion.emotion.value,
            emotion_intensity=emotion.intensity,
        )
    messages = chat_history.get_messages(user_id)

    rel_level = relationship_tracker.update(
        user_id, emotion=emotion.emotion.value, base_level=persona.relationship_level,
        persona_id=persona_id,
    )

    time_context = _get_time_context()
    memory_context = memory_mgr.get_context_prompt(user_id, limit=8)

    # 记忆检索：找到与当前消息相关的记忆
    relevant_memories = await _retrieve_relevant_memories(user_id, content, llm)
    relevant_context = ""
    if relevant_memories:
        relevant_context = "\n【与当前话题相关的记忆】\n" + "\n".join(f"- {m}" for m in relevant_memories)

    # 构建 extra_instructions，多消息时增加上下文说明
    extra_instructions = f"时间：{time_context}\n用户当前情绪：{emotion.emotion.value}（强度 {emotion.intensity}）"
    if msg_count > 1:
        extra_instructions += (
            f"\n【重要】用户连续发了 {msg_count} 条消息，这是用户在短时间内快速输入的碎片化想法。"
            f"请把它们作为一个整体来理解用户的情绪和意图，"
            f"回复时自然地回应所有内容，不要逐条回复，也不要提到「你发了很多消息」之类的话。"
            f"像真人聊天一样，抓住重点，整体回应。"
        )

    system_prompt = PromptBuilder.build(
        persona,
        memory_context=memory_context + relevant_context,
        extra_instructions=extra_instructions,
        relationship_level=rel_level,
    )

    # 保存供 /debug 查看
    _last_system_prompt = system_prompt

    # 流式输出 vs 非流式
    reply = ""
    if on_token:
        # 流式：逐 token 调用回调（带错误处理）
        try:
            async for token in llm.chat_stream(messages=messages, system_prompt=system_prompt):
                on_token(token)
                reply += token
        except Exception as e:
            logger.error(f"LLM stream failed: {e}")
            error_msg = _get_llm_error_message(e)
            return error_msg, rel_level
    else:
        try:
            response = await llm.chat(messages=messages, system_prompt=system_prompt)
            reply = response.content
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            error_msg = _get_llm_error_message(e)
            return error_msg, rel_level

    reply = EmotionEnhancer.enhance_reply(reply, emotion)

    chat_history.add_message(user_id, "assistant", reply)
    chat_history.add_short_memory(user_id, content, reply)

    # 基础记忆存储（关键词评分）
    memory_mgr.add_memory(user_id, content)

    # LLM 辅助记忆提取（异步，不阻塞用户）
    _run_background_task(_background_extract_memory(user_id, content, reply, llm))

    # 异步总结（不阻塞用户）
    short_memories = chat_history.get_short_memories(user_id)
    if len(short_memories) >= ADVANCED["summarize_threshold"]:
        _run_background_task(_background_summarize(user_id, llm, short_memories))

    logger.debug(f"[{persona.name}] → {user_id}: {reply[:80]}...")
    return reply, rel_level


def _run_background_task(coro):
    """运行后台任务，保持引用防止 GC"""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def _get_llm_error_message(error: Exception) -> str:
    """将 LLM 异常转为用户友好的中文消息"""
    error_str = str(error).lower()
    if "rate" in error_str or "429" in error_str:
        return "模型太忙了，稍等一下再试~ 🥺"
    elif "auth" in error_str or "401" in error_str or "api_key" in error_str:
        return "API key 好像有问题，检查一下配置哦~"
    elif "timeout" in error_str:
        return "网络有点慢，再试一次？"
    elif "connection" in error_str or "connect" in error_str:
        return "网络好像断了，检查一下网络连接~"
    else:
        return "哎呀，出了点小问题，再试一次？"


async def _background_summarize(user_id: str, llm, short_memories: list):
    """后台执行记忆总结"""
    try:
        summarizer = MemorySummarizer(llm)
        summary = await summarizer.summarize(short_memories)
        if summary:
            memory_mgr.add_memory(user_id, summary, level=4, tags=["总结"])
            chat_history.clear_short_memories(user_id)
            logger.info(f"Short memory summarized for {user_id}")
    except Exception as e:
        logger.warning(f"Background summarization failed: {e}")


async def _background_extract_memory(user_id: str, user_msg: str, assistant_reply: str, llm):
    """后台用 LLM 从对话中提取值得记住的信息"""
    try:
        summarizer = MemorySummarizer(llm)
        extracted = await summarizer.extract_memory(user_msg, assistant_reply)
        if extracted and extracted.get("content"):
            content = extracted["content"]
            importance = extracted.get("importance", 3)
            # 只有重要度 >= 2 才存储
            if importance >= 2:
                memory_mgr.add_memory(user_id, content, level=importance, tags=["自动提取"])
                logger.info(f"Auto-extracted memory [{importance}★]: {content[:30]}...")
    except Exception as e:
        logger.debug(f"Background memory extraction failed: {e}")


async def _retrieve_relevant_memories(user_id: str, query: str, llm) -> list[str]:
    """检索与当前消息相关的记忆"""
    try:
        # 获取所有记忆的内容
        all_memories = memory_mgr.get_memories(user_id, limit=30)
        if not all_memories:
            return []

        memory_texts = [m.content for m in all_memories]

        summarizer = MemorySummarizer(llm)
        relevant = await summarizer.retrieve_relevant(query, memory_texts, limit=3)
        return relevant
    except Exception as e:
        logger.debug(f"Memory retrieval failed: {e}")
        return []


# ========== 思考中动画 ==========
_SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
_SPINNER_TEXT = " 正在思考..."


async def _spinner_task(stop_event: asyncio.Event, persona_name: str):
    """后台 spinner 协程，每 0.12s 刷新一帧"""
    frame = 0
    while not stop_event.is_set():
        icon = _SPINNER_FRAMES[frame % len(_SPINNER_FRAMES)]
        print(f"\r  {Colors.DIM}{icon}{_SPINNER_TEXT}{Colors.RESET}", end="", flush=True)
        frame += 1
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=0.12)
            break  # stop_event 已设置
        except asyncio.TimeoutError:
            pass  # 继续动画


# ========== 打印回复（统一逻辑） ==========
async def _print_reply(persona_name: str, reply: str):
    """分段打印 AI 回复（非流式回退用）"""
    segmented = MessageSegmenter.segment(reply, max_segment_length=ADVANCED["segment_max_length"])
    for i, seg in enumerate(segmented.segments):
        if i == 0:
            print(f"\n{Colors.MAGENTA}{persona_name}:{Colors.RESET} {seg}", end="", flush=True)
        else:
            try:
                delay = MessageSegmenter.get_typing_delay(i, segmented.total_segments)
            except AttributeError:
                delay = 0
            if delay > 0:
                await asyncio.sleep(delay)
            print(f"\n  {seg}", end="", flush=True)
    print()


def _print_reply_token(persona_name: str, token: str, is_first: bool) -> bool:
    """流式打印一个 token，返回是否已打印过内容"""
    if is_first:
        print(f"\n{Colors.MAGENTA}{persona_name}:{Colors.RESET} ", end="", flush=True)
    print(token, end="", flush=True)
    return False


# ========== 聊天循环 ==========
async def chat_loop():
    """终端聊天（支持消息累积去抖 + 斜杠命令）"""
    global _current_persona_id

    persona = persona_loader.get(_current_persona_id)
    persona_name = persona.name if persona else "小雨"
    debounce_seconds = ADVANCED.get("debounce_seconds", 3)
    user_id = "local_user"

    if not registry.available_models:
        logger.error("没有可用的模型！请先运行: python main.py setup")
        return

    # 会话统计
    stats = SessionStats()
    stats.start_level = relationship_tracker.get_level(
        user_id, base_level=persona.relationship_level, persona_id=_current_persona_id
    )
    last_reply = [""]  # 跟踪最近一次回复，用于 Ctrl+C 时保存

    logger.info(f"模型: {registry.get().model_name}")
    logger.info(f"人设: {persona_name}")

    # 欢迎语
    welcome = _get_welcome_message(persona, stats.start_level)
    print(f"\n{Colors.MAGENTA}{persona_name}:{Colors.RESET} {welcome}")
    print(f"{Colors.DIM}输入 /help 查看可用命令{Colors.RESET}")
    if debounce_seconds > 0:
        print(f"{Colors.DIM}消息累积: 输入后 {debounce_seconds} 秒内可继续输入，合并后一起发送{Colors.RESET}")
    print()

    message_queue: list[str] = []
    input_q: queue.Queue[str | None] = queue.Queue()
    proactive_q: queue.Queue[str] = queue.Queue()  # 主动消息队列

    def _input_reader():
        """独立线程：持续读取用户输入"""
        while True:
            try:
                line = input(f"{Colors.CYAN}你:{Colors.RESET} ").strip()
                if not line:
                    continue  # 空输入（直接回车）跳过
                input_q.put(line)
            except (EOFError, KeyboardInterrupt):
                input_q.put(None)
                break

    # 启动输入线程
    input_thread = threading.Thread(target=_input_reader, daemon=True)
    input_thread.start()

    try:
        while True:
            # 等待用户输入，超时时间 = debounce_seconds
            try:
                user_input = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: input_q.get(timeout=debounce_seconds)
                )
            except (queue.Empty, Exception) as e:
                if not isinstance(e, queue.Empty):
                    raise
                # 超时 → 检查主动消息 or 发送累积的消息
                if not message_queue:
                    # 检查是否有主动消息
                    proactive_msg = proactive.check_proactive_messages(
                        user_id, _current_persona_id
                    )
                    if proactive_msg:
                        persona_obj = persona_loader.get(_current_persona_id)
                        p_name = persona_obj.name if persona_obj else "AI"
                        print(f"\n{Colors.YELLOW}💌 {p_name} 主动找你：{Colors.RESET}")
                        print(f"{Colors.MAGENTA}{p_name}:{Colors.RESET} {proactive_msg}")
                        print(f"{Colors.DIM}（AI 主动消息，无需回复~）{Colors.RESET}\n")
                    continue

                count = len(message_queue)
                combined = "\n".join(message_queue)
                message_queue = []

                # 流式输出：定义 token 回调
                first_token = [True]
                spinner_stop = asyncio.Event()

                def _on_token(token: str):
                    nonlocal first_token
                    last_reply[0] += token
                    if first_token[0]:
                        spinner_stop.set()
                        print(f"\r{' ' * 50}\r", end="", flush=True)
                        _print_reply_token(persona_name, token, True)
                        first_token[0] = False
                    else:
                        _print_reply_token(persona_name, token, False)

                # 启动 spinner
                spinner = asyncio.create_task(_spinner_task(spinner_stop, persona_name))

                reply, rel_level = await handle_message(
                    user_id, combined, persona_id=_current_persona_id, on_token=_on_token
                )

                # 确保 spinner 停止
                if not spinner_stop.is_set():
                    spinner_stop.set()
                spinner.cancel()
                stats.message_count += count
                stats.end_level = rel_level

                # 流式已逐字打印完毕，只需换行
                if not first_token[0]:
                    print()
                else:
                    # 非流式回退（如无模型时）
                    await _print_reply(persona_name, reply)

                _print_rel_change(rel_level)
                last_reply[0] = ""  # 重置，准备下一条消息
                continue

            # 收到输入
            if user_input is None or user_input.lower() in ("quit", "/quit"):
                break

            # 斜杠命令
            if user_input.startswith("/"):
                result = await handle_command(user_input, user_id, persona_name)
                if result == "quit":
                    break
                if result is True:
                    continue

            # 不用去抖模式
            if debounce_seconds <= 0:
                stats.message_count += 1

                # 流式输出 + spinner
                first_token = [True]
                spinner_stop = asyncio.Event()

                def _on_token_direct(token: str):
                    last_reply[0] += token
                    if first_token[0]:
                        spinner_stop.set()
                        _print_reply_token(persona_name, token, True)
                        first_token[0] = False
                    else:
                        _print_reply_token(persona_name, token, False)

                spinner = asyncio.create_task(_spinner_task(spinner_stop, persona_name))

                reply, rel_level = await handle_message(
                    user_id, user_input, persona_id=_current_persona_id, on_token=_on_token_direct
                )

                if not spinner_stop.is_set():
                    spinner_stop.set()
                spinner.cancel()
                stats.end_level = rel_level
                if not first_token[0]:
                    print()
                else:
                    await _print_reply(persona_name, reply)
                _print_rel_change(rel_level)
                last_reply[0] = ""  # 重置，准备下一条消息
                continue

            # 加入消息队列
            message_queue.append(user_input)
            count = len(message_queue)
            if count == 1:
                print(f"  {Colors.DIM}⏳ 等待更多消息...（{debounce_seconds} 秒后发送）{Colors.RESET}", flush=True)
            else:
                print(f"  {Colors.DIM}✓ 已收集 {count} 条消息，继续输入或等待发送{Colors.RESET}", flush=True)

    except asyncio.CancelledError:
        # Ctrl+C 中断时保存已生成的部分回复
        if last_reply[0]:
            chat_history.add_message(user_id, "assistant", last_reply[0])
            print(f"\n{Colors.DIM}（已保存部分回复）{Colors.RESET}")
    finally:
        # 清理输入线程
        input_q.put(None)

    # 退出总结
    stats.end_level = relationship_tracker.get_level(
        user_id, base_level=persona.relationship_level, persona_id=_current_persona_id
    )
    print(stats.summary(persona_name))


def _print_rel_change(level: int):
    """显示亲密度变化提示"""
    if level >= 80:
        icon = "💕"
    elif level >= 60:
        icon = "💗"
    elif level >= 40:
        icon = "💛"
    else:
        icon = "🤍"
    print(f"  {Colors.DIM}{icon} 亲密度 {level}/100{Colors.RESET}")


# ========== 主入口 ==========
def main():
    import argparse

    parser = argparse.ArgumentParser(description="🎀 Cyber Girlfriend")
    parser.add_argument(
        "command",
        nargs="?",
        default="run",
        choices=["setup", "run"],
        help="setup=设置向导, run=开始聊天（默认）",
    )
    args = parser.parse_args()

    if args.command == "setup":
        from setup import run_setup
        run_setup()
        return

    if not (ROOT / ".env").exists():
        logger.warning("未检测到 .env 文件，请先运行: python main.py setup")
        return

    logger.info("🎀 Cyber Girlfriend 启动中...")
    try:
        asyncio.run(chat_loop())
    except KeyboardInterrupt:
        print()
        logger.info("拜拜~")


if __name__ == "__main__":
    main()
