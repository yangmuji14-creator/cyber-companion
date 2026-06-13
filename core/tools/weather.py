"""天气工具 — 获取指定城市的天气信息

当前使用模拟数据（mock），后续可接入真实天气 API。
"""

import random
from datetime import datetime

from .base import BaseTool, ToolResult


# 城市天气模拟数据
_MOCK_WEATHER: dict[str, list[dict]] = {
    "北京": [
        {"condition": "晴", "temp": 28, "humidity": 40, "wind": "3级"},
        {"condition": "多云", "temp": 25, "humidity": 50, "wind": "2级"},
        {"condition": "晴", "temp": 30, "humidity": 35, "wind": "3级"},
    ],
    "上海": [
        {"condition": "多云", "temp": 26, "humidity": 65, "wind": "3级"},
        {"condition": "小雨", "temp": 23, "humidity": 80, "wind": "2级"},
        {"condition": "阴", "temp": 24, "humidity": 70, "wind": "2级"},
    ],
    "广州": [
        {"condition": "阵雨", "temp": 30, "humidity": 78, "wind": "2级"},
        {"condition": "雷阵雨", "temp": 28, "humidity": 85, "wind": "3级"},
        {"condition": "多云", "temp": 31, "humidity": 72, "wind": "2级"},
    ],
    "深圳": [
        {"condition": "多云", "temp": 29, "humidity": 75, "wind": "2级"},
        {"condition": "阵雨", "temp": 27, "humidity": 82, "wind": "3级"},
        {"condition": "晴", "temp": 31, "humidity": 68, "wind": "2级"},
    ],
    "成都": [
        {"condition": "阴", "temp": 24, "humidity": 72, "wind": "1级"},
        {"condition": "小雨", "temp": 21, "humidity": 80, "wind": "2级"},
        {"condition": "多云", "temp": 25, "humidity": 65, "wind": "2级"},
    ],
    "杭州": [
        {"condition": "晴", "temp": 27, "humidity": 55, "wind": "2级"},
        {"condition": "多云", "temp": 25, "humidity": 62, "wind": "2级"},
        {"condition": "小雨", "temp": 22, "humidity": 78, "wind": "3级"},
    ],
}

_DEFAULT_WEATHER = [
    {"condition": "晴", "temp": 26, "humidity": 50, "wind": "2级"},
    {"condition": "多云", "temp": 24, "humidity": 55, "wind": "2级"},
    {"condition": "晴", "temp": 28, "humidity": 45, "wind": "3级"},
]

# 天气建议
_WEATHER_ADVICE = {
    "晴": "天气不错，适合出门走走",
    "多云": "天气还行，可以出门",
    "阴": "天气阴沉，记得带伞以防万一",
    "小雨": "有小雨，记得带伞",
    "阵雨": "有阵雨，出门带伞",
    "雷阵雨": "有雷阵雨，尽量待在室内",
    "大雨": "有大雨，尽量减少外出",
    "雪": "下雪了，注意保暖",
}


class WeatherTool(BaseTool):
    """天气查询工具（当前使用模拟数据）"""

    @property
    def name(self) -> str:
        return "get_weather"

    @property
    def description(self) -> str:
        return "查询某个城市的当前天气和未来天气预报"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "城市名称，如 北京、上海、广州",
                }
            },
            "required": ["city"],
        }

    async def execute(self, city: str) -> ToolResult:
        day_index = datetime.now().day % 3
        weather_data = _MOCK_WEATHER.get(city, _DEFAULT_WEATHER)
        today = weather_data[day_index] if day_index < len(weather_data) else weather_data[0]

        condition = today["condition"]
        advice = _WEATHER_ADVICE.get(condition, "")

        output = (
            f"{city} 当前天气：{condition}，"
            f"温度 {today['temp']}°C，"
            f"湿度 {today['humidity']}%，"
            f"风力 {today['wind']}。"
        )
        if advice:
            output += f"\n建议：{advice}"

        # 添加未来两天预报
        if len(weather_data) >= 2:
            forecast_lines = ["\n未来预报："]
            for i in range(1, min(3, len(weather_data))):
                f = weather_data[(day_index + i) % len(weather_data)]
                forecast_lines.append(
                    f"  - 第{i}天：{f['condition']}，{f['temp']}°C"
                )
            output += "".join(forecast_lines)

        return ToolResult(
            success=True,
            output=output,
            data={
                "city": city,
                "condition": condition,
                "temperature": today["temp"],
                "humidity": today["humidity"],
                "wind": today["wind"],
                "advice": advice,
            },
        )
