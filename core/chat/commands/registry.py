"""命令注册表 — COMMANDS 字典"""

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
