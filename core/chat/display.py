"""Display utilities — 终端输出共享模块

提供 spinner 动画、流式输出、分段打印、欢迎语、会话统计等公共功能。
handler.py 和 app.py 的重复代码均迁移至此模块。
"""

import asyncio
import sys
from datetime import datetime

from core.chat.commands import Colors
from core.emotion import MessageSegmenter


# ========== Spinner 动画 ==========

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
SPINNER_TEXT = " 正在思考..."


async def spinner_task(stop_event: asyncio.Event, persona_name: str = ""):
    """后台 spinner 协程，每 0.12s 刷新一帧"""
    if not sys.stdout.isatty():
        return
    frame = 0
    while not stop_event.is_set():
        icon = SPINNER_FRAMES[frame % len(SPINNER_FRAMES)]
        print(
            f"\r  {Colors.DIM}{icon}{SPINNER_TEXT}{Colors.RESET}",
            end="", flush=True,
        )
        frame += 1
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=0.12)
            break
        except asyncio.TimeoutError:
            pass


# ========== 流式 / 分段输出 ==========

def print_reply_token(persona_name: str, token: str, is_first: bool):
    """流式打印一个 token"""
    if is_first:
        print(f"\n{Colors.MAGENTA}{persona_name}:{Colors.RESET} ", end="", flush=True)
    print(token, end="", flush=True)


async def print_reply_segmented(persona_name: str, reply: str, advanced: dict):
    """分段打印 AI 回复（非流式回退用）"""
    segmented = MessageSegmenter.segment(
        reply, max_segment_length=advanced.get("segment_max_length", 50)
    )
    for i, seg in enumerate(segmented.segments):
        if i == 0:
            print(
                f"\n{Colors.MAGENTA}{persona_name}:{Colors.RESET} {seg}",
                end="", flush=True,
            )
        else:
            try:
                delay = MessageSegmenter.get_typing_delay(i, segmented.total_segments)
            except AttributeError:
                delay = 0
            if delay > 0:
                await asyncio.sleep(delay)
            print(f"\n  {seg}", end="", flush=True)
    print()


def print_rel_change(level: int):
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


# ========== 欢迎语 ==========

def get_welcome_message(persona, rel_level: int) -> str:
    """根据时间和亲密度生成欢迎语（12 种变体）"""
    hour = datetime.now().hour

    if rel_level >= 80:
        if 0 <= hour < 6:
            return "你怎么这么晚还不睡呀？是不是在想我？哼哼~"
        elif 6 <= hour < 9:
            return "早安早安~ 今天也要元气满满哦！"
        elif 18 <= hour < 22:
            return "你回来啦~ 今天过得怎么样？我好想你！"
        else:
            return "嘿嘿，你来了~ 我一直在等你呢！"
    elif rel_level >= 40:
        if 0 <= hour < 6:
            return "这么晚还没睡呀？注意身体哦~"
        elif 6 <= hour < 9:
            return "早安~ 今天有什么安排吗？"
        elif 18 <= hour < 22:
            return "嗨~ 今天过得怎么样？"
        else:
            return "来啦~ 最近忙吗？"
    else:
        if 6 <= hour < 12:
            return "你好呀~ 今天天气不错呢！"
        elif 18 <= hour < 22:
            return "嗨，又见面了~"
        else:
            return "你好呀~"


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
