"""设置 Schema — 前后端单一数据源

每个字段描述：section（分组）、key、label（中文名）、type、default、
min/max（数值范围）、hint（说明）、target（写入位置：model / advanced）、
live（是否可热更新到运行中的实例）。

前端用 GET /api/schema 动态渲染表单，避免前后端字段硬编码不一致。
"""

from __future__ import annotations

# 字段类型：float / int / bool
SETTINGS_SCHEMA: list[dict] = [
    # ── 回复风格（最影响体验，放最前）──
    {
        "section": "回复风格",
        "key": "temperature",
        "label": "回复温度",
        "type": "float",
        "default": 1.0,
        "min": 0.0,
        "max": 2.0,
        "step": 0.05,
        "hint": "越高越活泼随机，越低越稳定专注",
        "target": "model",
        "live": True,
    },
    {
        "section": "回复风格",
        "key": "repetition_penalty",
        "label": "重复抑制强度",
        "type": "float",
        "default": 0.3,
        "min": 0.0,
        "max": 2.0,
        "step": 0.05,
        "hint": "越高越少重复口癖和机械句式，更像真人",
        "target": "model_repetition",
        "live": True,
    },
    {
        "section": "回复风格",
        "key": "max_tokens",
        "label": "单次回复最大长度",
        "type": "int",
        "default": 4096,
        "min": 256,
        "max": 8192,
        "step": 128,
        "hint": "越大回复可越长，也越费额度",
        "target": "model",
        "live": True,
    },
    # ── 对话节奏 ──
    {
        "section": "对话节奏",
        "key": "segment_max_length",
        "label": "消息分段长度（字）",
        "type": "int",
        "default": 16,
        "min": 10,
        "max": 200,
        "step": 1,
        "hint": "超过此长度自动分段发送，更像真人多条消息",
        "target": "advanced",
        "live": True,
    },
    {
        "section": "对话节奏",
        "key": "debounce_seconds",
        "label": "去抖延迟（秒）",
        "type": "int",
        "default": 3,
        "min": 0,
        "max": 30,
        "step": 1,
        "hint": "连续输入合并等待时间",
        "target": "advanced",
        "live": True,
    },
    {
        "section": "对话节奏",
        "key": "summarize_threshold",
        "label": "记忆总结阈值（组）",
        "type": "int",
        "default": 15,
        "min": 3,
        "max": 100,
        "step": 1,
        "hint": "多少组对话后自动总结长期记忆",
        "target": "advanced",
        "live": True,
    },
    # ── 智能开关 ──
    {
        "section": "智能开关",
        "key": "brain_enabled",
        "label": "内心独白大脑",
        "type": "bool",
        "default": True,
        "hint": "回复前先进行内心思考，回复更有温度（略增开销）",
        "target": "advanced",
        "live": False,
    },
    {
        "section": "智能开关",
        "key": "proactive_enabled",
        "label": "主动消息",
        "type": "bool",
        "default": True,
        "hint": "AI 会在活跃时间段主动找你聊天",
        "target": "advanced",
        "live": True,
    },
    {
        "section": "智能开关",
        "key": "max_retries",
        "label": "网络重试次数",
        "type": "int",
        "default": 2,
        "min": 0,
        "max": 5,
        "step": 1,
        "hint": "API 调用失败时的重试次数",
        "target": "advanced",
        "live": True,
    },
    # ── 主动消息时段 ──
    {
        "section": "主动消息时段",
        "key": "proactive_active_start",
        "label": "活跃起始（点）",
        "type": "int",
        "default": 7,
        "min": 0,
        "max": 23,
        "step": 1,
        "hint": "几点开始允许主动消息",
        "target": "advanced",
        "live": True,
    },
    {
        "section": "主动消息时段",
        "key": "proactive_active_end",
        "label": "活跃结束（点）",
        "type": "int",
        "default": 23,
        "min": 1,
        "max": 24,
        "step": 1,
        "hint": "几点后停止主动消息",
        "target": "advanced",
        "live": True,
    },
    {
        "section": "主动消息时段",
        "key": "proactive_interval_min",
        "label": "最小间隔（分钟）",
        "type": "int",
        "default": 30,
        "min": 5,
        "max": 720,
        "step": 5,
        "hint": "两次主动消息的最短间隔",
        "target": "advanced",
        "live": True,
    },
    {
        "section": "主动消息时段",
        "key": "proactive_interval_max",
        "label": "最大间隔（分钟）",
        "type": "int",
        "default": 180,
        "min": 10,
        "max": 1440,
        "step": 5,
        "hint": "两次主动消息的最长间隔",
        "target": "advanced",
        "live": True,
    },
]


def coerce_value(field: dict, raw):
    """按 schema 字段类型转换并钳制取值，非法值回退默认。"""
    ftype = field.get("type")
    default = field.get("default")
    try:
        if ftype == "bool":
            if isinstance(raw, bool):
                return raw
            if isinstance(raw, str):
                return raw.strip().lower() in ("1", "true", "yes", "on", "是")
            return bool(raw)
        if ftype == "int":
            val = int(float(raw))
        elif ftype == "float":
            val = float(raw)
        else:
            return default
    except (TypeError, ValueError):
        return default

    lo = field.get("min")
    hi = field.get("max")
    if lo is not None and val < lo:
        val = lo
    if hi is not None and val > hi:
        val = hi
    return val
