"""内置工具集 — 给 AI 角色可以使用的工具"""

import json
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger

from .base import Tool, ToolResult, ToolRegistry


class ClockTool(Tool):
    """查看当前时间"""

    name = "clock"
    description = "查看当前日期和时间，包括星期几"

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, **kwargs) -> ToolResult:
        now = datetime.now()
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        output = (
            f"当前时间：{now.strftime('%Y年%m月%d日')} "
            f"{weekdays[now.weekday()]} "
            f"{now.strftime('%H:%M')}"
        )
        return ToolResult(True, output)


class DateCalcTool(Tool):
    """日期计算"""

    name = "date_calc"
    description = "计算两个日期之间的天数差"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "date1": {"type": "string", "description": "第一个日期 YYYY-MM-DD"},
                "date2": {"type": "string", "description": "第二个日期 YYYY-MM-DD"},
            },
            "required": ["date1"],
        }

    async def execute(self, date1: str = "", date2: str = "") -> ToolResult:
        try:
            d1 = datetime.strptime(date1, "%Y-%m-%d")
            d2 = datetime.strptime(date2, "%Y-%m-%d") if date2 else datetime.now()
            delta = abs((d2 - d1).days)
            return ToolResult(True, f"从 {date1} 到 {d2.strftime('%Y-%m-%d')} 共 {delta} 天")
        except ValueError as e:
            return ToolResult(False, "", f"日期格式错误: {e}")


class ReminderTool(Tool):
    """设置提醒（持久化到文件）"""

    name = "reminder"
    description = "记录一个提醒事项，以后可以查看"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "提醒内容"},
            },
            "required": ["content"],
        }

    def __init__(self, data_dir: str = ""):
        self._path = Path(data_dir) / "reminders" if data_dir else Path("data/reminders")
        self._path.mkdir(parents=True, exist_ok=True)

    async def execute(self, content: str = "") -> ToolResult:
        if not content:
            return ToolResult(False, "", "请告诉我需要记住什么")
        now = datetime.now()
        file = self._path / f"{now.strftime('%Y%m')}.json"
        reminders = []
        if file.exists():
            reminders = json.loads(file.read_text(encoding="utf-8"))
        reminders.append({
            "content": content,
            "created_at": now.isoformat(),
        })
        file.write_text(
            json.dumps(reminders, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(f"Saved reminder: {content}")
        return ToolResult(True, f"已记住：{content}")


class NoteTool(Tool):
    """快速笔记"""

    name = "note"
    description = "记录一段笔记/日记，存档到本地文件"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "笔记内容"},
                "tags": {"type": "string", "description": "标签，用逗号分隔"},
            },
            "required": ["content"],
        }

    def __init__(self, data_dir: str = ""):
        self._path = Path(data_dir) / "notes" if data_dir else Path("data/notes")
        self._path.mkdir(parents=True, exist_ok=True)

    async def execute(self, content: str = "", tags: str = "") -> ToolResult:
        if not content:
            return ToolResult(False, "", "内容不能为空")
        now = datetime.now()
        file = self._path / f"{now.strftime('%Y%m%d')}.md"
        tag_line = f"tags: {tags}\n" if tags else ""
        entry = f"\n## {now.strftime('%H:%M')}\n{tag_line}{content}\n---\n"
        with open(file, "a", encoding="utf-8") as f:
            f.write(entry)
        logger.info(f"Saved note: {content[:30]}...")
        return ToolResult(True, f"已保存笔记")


class TimerTool(Tool):
    """倒计时提醒（内存中计时）"""

    name = "timer"
    description = "设置一个倒计时，指定分钟后提醒"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "minutes": {"type": "integer", "description": "多少分钟后提醒"},
                "note": {"type": "string", "description": "提醒内容"},
            },
            "required": ["minutes"],
        }
    _timers: list[dict] = []

    async def execute(self, minutes: int = 1, note: str = "") -> ToolResult:
        if minutes < 1 or minutes > 1440:
            return ToolResult(False, "", "倒计时时间应在 1~1440 分钟之间")
        now = datetime.now()
        eta = now + timedelta(minutes=minutes)
        text = f"将在 {minutes} 分钟后（{eta.strftime('%H:%M')}）提醒：{note or '时间到'}"
        TimerTool._timers.append({
            "note": note or "时间到",
            "eta": eta,
        })
        return ToolResult(True, text)

    @classmethod
    def check(cls) -> list[str]:
        overdue = []
        now = datetime.now()
        remaining = []
        for t in cls._timers:
            if now >= t["eta"]:
                overdue.append(t["note"])
            else:
                remaining.append(t)
        cls._timers[:] = remaining
        return overdue


class TranslateTool(Tool):
    """文本翻译（中英互译）"""

    name = "translate"
    description = "翻译文本（中英互译，无需 API）"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "需要翻译的文本"},
                "target": {"type": "string", "description": "目标语言：zh 或 en"},
            },
            "required": ["text"],
        }

    _dict = {
        "早上好": "Good morning",
        "晚上好": "Good evening",
        "你好": "Hello",
        "谢谢": "Thank you",
        "再见": "Goodbye",
        "今天": "today",
        "明天": "tomorrow",
        "昨天": "yesterday",
        "开心": "happy",
        "难过": "sad",
        "天气": "weather",
        "学习": "study",
        "工作": "work",
        "Hello": "你好",
        "Good morning": "早上好",
        "Good evening": "晚上好",
        "Thank you": "谢谢",
        "Goodbye": "再见",
        "today": "今天",
        "tomorrow": "明天",
        "yesterday": "昨天",
        "happy": "开心",
        "sad": "难过",
        "weather": "天气",
        "study": "学习",
        "work": "工作",
    }

    async def execute(self, text: str = "", target: str = "zh") -> ToolResult:
        if not text:
            return ToolResult(False, "", "请提供需要翻译的文本")
        target = target.lower()
        if target not in ("zh", "en"):
            target = "zh"
        result = self._dict.get(text.strip(), f"[翻译] {text}")
        return ToolResult(True, result)


def register_all(registry: ToolRegistry, data_dir: str = "") -> None:
    """注册所有内置工具"""
    registry.register(ClockTool())
    registry.register(DateCalcTool())
    registry.register(ReminderTool(data_dir))
    registry.register(NoteTool(data_dir))
    registry.register(TimerTool())
    registry.register(TranslateTool())
