"""时间/日期工具 — 获取当前时间、日期、星期等信息"""

from datetime import datetime

from .base import BaseTool, ToolResult


class TimeTool(BaseTool):
    """获取当前时间和日期信息"""

    @property
    def name(self) -> str:
        return "get_current_time"

    @property
    def description(self) -> str:
        return "获取当前日期、时间、星期、季节等信息"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "enum": ["full", "date", "time", "weekday"],
                    "description": "信息格式：full=全部, date=日期, time=时间, weekday=星期",
                    "default": "full",
                }
            },
            "required": [],
        }

    async def execute(self, format: str = "full") -> ToolResult:
        now = datetime.now()
        weekdays_cn = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        weekday_cn = weekdays_cn[now.weekday()]

        # 判断季节
        month = now.month
        if 3 <= month <= 5:
            season = "春天"
        elif 6 <= month <= 8:
            season = "夏天"
        elif 9 <= month <= 11:
            season = "秋天"
        else:
            season = "冬天"

        if format == "date":
            output = f"{now.strftime('%Y年%m月%d日')}，{weekday_cn}"
        elif format == "time":
            output = f"{now.strftime('%H:%M:%S')}"
        elif format == "weekday":
            output = f"{weekday_cn}"
        else:
            output = (
                f"现在是 {now.strftime('%Y年%m月%d日')} {now.strftime('%H:%M')}，"
                f"{weekday_cn}，{season}"
            )

        return ToolResult(
            success=True,
            output=output,
            data={
                "datetime": now.isoformat(),
                "date": now.strftime("%Y-%m-%d"),
                "time": now.strftime("%H:%M:%S"),
                "weekday": weekday_cn,
                "season": season,
                "timestamp": int(now.timestamp()),
            },
        )
