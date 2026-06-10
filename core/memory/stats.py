"""聊天数据统计模块

从 chat_history 数据生成统计信息和 ASCII 可视化图表。
"""

from collections import Counter, defaultdict
from datetime import datetime, timedelta

from loguru import logger


# 情感中文名映射
EMOTION_LABELS = {
    "happy": "开心",
    "sad": "难过",
    "angry": "生气",
    "neutral": "中性",
    "excited": "兴奋",
    "lonely": "孤独",
    "anxious": "焦虑",
    "love": "爱意",
}


class ChatStats:
    """聊天数据统计器"""

    def __init__(self, messages: list[dict]):
        """
        Args:
            messages: chat_history.get_messages() 返回的消息列表
        """
        self._messages = messages
        self._parsed = self._parse_messages(messages)

    @staticmethod
    def _parse_messages(messages: list[dict]) -> list[dict]:
        """解析消息，提取时间、情感等元数据"""
        parsed = []
        for msg in messages:
            ts_str = msg.get("timestamp", "")
            dt = None
            if ts_str:
                try:
                    dt = datetime.fromisoformat(ts_str)
                except (ValueError, TypeError):
                    pass

            parsed.append({
                "role": msg.get("role", ""),
                "content": msg.get("content", ""),
                "timestamp": dt,
                "emotion": msg.get("emotion"),
                "emotion_intensity": msg.get("emotion_intensity"),
            })
        return parsed

    def total_messages(self) -> int:
        """总消息数"""
        return len(self._parsed)

    def user_messages(self) -> int:
        """用户消息数"""
        return sum(1 for m in self._parsed if m["role"] == "user")

    def assistant_messages(self) -> int:
        """AI 消息数"""
        return sum(1 for m in self._parsed if m["role"] == "assistant")

    def avg_message_length(self) -> float:
        """平均消息长度"""
        if not self._parsed:
            return 0
        total_len = sum(len(m["content"]) for m in self._parsed)
        return total_len / len(self._parsed)

    def hourly_distribution(self) -> dict[int, int]:
        """按小时分布的消息数量（0-23）"""
        dist: dict[int, int] = {h: 0 for h in range(24)}
        for m in self._parsed:
            if m["timestamp"]:
                dist[m["timestamp"].hour] += 1
        return dist

    def emotion_distribution(self) -> dict[str, int]:
        """情感分布统计"""
        counter: Counter = Counter()
        for m in self._parsed:
            if m["emotion"]:
                counter[m["emotion"]] += 1
        return dict(counter.most_common())

    def daily_message_counts(self, days: int = 7) -> dict[str, int]:
        """最近 N 天每天的消息数"""
        today = datetime.now().date()
        counts: dict[str, int] = {}
        for i in range(days - 1, -1, -1):
            date = today - timedelta(days=i)
            counts[date.strftime("%m/%d")] = 0

        for m in self._parsed:
            if m["timestamp"]:
                date_key = m["timestamp"].date().strftime("%m/%d")
                if date_key in counts:
                    counts[date_key] += 1
        return counts

    def most_active_hour(self) -> tuple[int, int]:
        """最活跃的小时和对应消息数"""
        dist = self.hourly_distribution()
        if not dist:
            return 0, 0
        best_hour = max(dist, key=dist.get)
        return best_hour, dist[best_hour]

    def peak_to_trough_ratio(self) -> float:
        """峰谷比（最活跃小时 / 最不活跃小时，排除 0）"""
        dist = self.hourly_distribution()
        values = [v for v in dist.values() if v > 0]
        if len(values) < 2:
            return 1.0
        return max(values) / min(values)


def _bar_horizontal(label: str, value: int, max_value: int, width: int = 20) -> str:
    """生成横向 ASCII 条形图"""
    if max_value == 0:
        bar_len = 0
    else:
        bar_len = int((value / max_value) * width)
    bar = "█" * bar_len
    return f"  {label:>4s} │ {bar} {value}"


def _bar_vertical(values: list[int], labels: list[str], height: int = 8) -> str:
    """生成纵向 ASCII 柱状图"""
    if not values or max(values) == 0:
        return "  (无数据)"

    max_val = max(values)
    lines = []
    for row in range(height, 0, -1):
        threshold = max_val * row / height
        line = "  "
        for v in values:
            if v >= threshold:
                line += "█ "
            else:
                line += "  "
        if row == height:
            line += f" {max_val}"
        elif row == height // 2:
            line += f" {max_val // 2}"
        lines.append(line)

    # x 轴标签
    label_line = "  " + " ".join(f"{l:>2s}" for l in labels)
    lines.append(label_line)
    return "\n".join(lines)


def _sparkline(values: list[int]) -> str:
    """生成迷你折线图（Unicode sparkline）"""
    if not values:
        return ""
    sparks = "▁▂▃▄▅▆▇█"
    max_val = max(values) if max(values) > 0 else 1
    result = ""
    for v in values:
        idx = int((v / max_val) * (len(sparks) - 1))
        result += sparks[idx]
    return result


def format_dashboard(stats: ChatStats) -> str:
    """生成完整的统计仪表盘文本"""
    lines = []

    # 标题
    lines.append(f"  {'─' * 44}")
    lines.append(f"  📊 聊天数据仪表盘")
    lines.append(f"  {'─' * 44}")

    # 基础统计
    lines.append(f"")
    lines.append(f"  💬 消息总数：{stats.total_messages()}")
    lines.append(f"     你：{stats.user_messages()} 条 | AI：{stats.assistant_messages()} 条")
    lines.append(f"     平均长度：{stats.avg_message_length():.0f} 字符")

    # 最活跃时段
    hour, count = stats.most_active_hour()
    lines.append(f"  ⏰ 最活跃时段：{hour}:00-{hour + 1}:00（{count} 条）")

    # 情感分布
    emotions = stats.emotion_distribution()
    if emotions:
        lines.append(f"")
        lines.append(f"  🎭 情感分布：")
        max_emo = max(emotions.values()) if emotions else 1
        for emo, cnt in emotions.items():
            label = EMOTION_LABELS.get(emo, emo)
            lines.append(_bar_horizontal(label, cnt, max_emo, width=15))

    # 每小时分布
    hourly = stats.hourly_distribution()
    # 只显示有消息的时段，或全部 24 小时
    active_hours = [(h, c) for h, c in hourly.items() if c > 0]
    if active_hours:
        lines.append(f"")
        lines.append(f"  ⏱  消息时间分布：")
        h_values = [c for _, c in active_hours]
        h_labels = [str(h) for h, _ in active_hours]
        # 如果时段太多，分组显示
        if len(active_hours) > 12:
            # 按 3 小时分组
            grouped: dict[str, int] = {}
            for h, c in active_hours:
                key = f"{h // 3 * 3:02d}"
                grouped[key] = grouped.get(key, 0) + c
            h_values = list(grouped.values())
            h_labels = [f"{k}h" for k in grouped.keys()]
        lines.append(_bar_vertical(h_values, h_labels, height=6))

    # 最近 7 天趋势
    daily = stats.daily_message_counts(7)
    if any(v > 0 for v in daily.values()):
        lines.append(f"")
        lines.append(f"  📈 最近 7 天趋势：")
        day_values = list(daily.values())
        day_labels = list(daily.keys())
        spark = _sparkline(day_values)
        lines.append(f"     {spark}")
        lines.append(f"     {' '.join(f'{l:>5s}' for l in day_labels)}")
        lines.append(f"     {' '.join(f'{v:>5d}' for v in day_values)}")

    lines.append(f"")
    lines.append(f"  {'─' * 44}")
    return "\n".join(lines)
