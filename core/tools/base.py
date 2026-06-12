"""ToolCalling — AI 工具调用系统

架构:
  Tool        — 单个工具的抽象（name, description, execute）
  ToolRegistry — 工具注册中心，管理注册 + prompt 生成 + 调用分发
  ToolCall    — AI 发起的工具调用请求
  ToolResult  — 工具执行结果

流程:
  1. ToolRegistry.get_prompt_block() → 注入 system prompt
  2. LLM 回复中包含 /tool name arg1 arg2 ... 或 markdown 格式
  3. ToolRegistry.parse_and_execute() → 解析执行
  4. 结果回传给 LLM 生成最终回复
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any

from loguru import logger


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    success: bool
    output: str
    error: str | None = None


class Tool:
    """工具基类"""

    name: str = ""
    description: str = ""
    parameters: list[dict] = []  # [{name, type, description, required}]

    async def execute(self, **kwargs) -> ToolResult:
        raise NotImplementedError


class ToolRegistry:
    """工具注册中心"""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool
        logger.debug(f"Registered tool: {tool.name}")

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[Tool]:
        return list(self._tools.values())

    def get_prompt_block(self) -> str:
        """生成注入 system prompt 的工具说明"""
        if not self._tools:
            return ""
        lines = ["【你可以使用的工具】"]
        for tool in self._tools.values():
            lines.append(f"\n--- {tool.name} ---")
            lines.append(f"说明：{tool.description}")
            if tool.parameters:
                for p in tool.parameters:
                    req = "（必填）" if p.get("required") else "（可选）"
                    lines.append(f"  - {p['name']} ({p.get('type', 'str')}){req}: {p.get('description', '')}")
            lines.append(f"使用方式：在回复中输出 /call {tool.name} 参数1=值1 参数2=值2")
        lines.append("\n当你认为需要用工具时，在回复中插入工具调用即可。")
        lines.append("工具调用对用户不可见，你仍然需要正常回复用户。")
        return "\n".join(lines)

    def parse_calls(self, text: str) -> list[ToolCall]:
        """从回复文本中解析工具调用

        支持格式：
          /call tool_name key1=value1 key2=value2
          或 ```tool_call\n{"name": "...", "args": {...}}\n```
        """
        calls: list[ToolCall] = []

        # 格式1：/call name k=v k=v
        for match in re.finditer(r'/call\s+(\w+)((?:\s+\w+=[^\s]+)*)', text):
            name = match.group(1)
            args_raw = match.group(2).strip()
            args: dict[str, Any] = {}
            if args_raw:
                for kv in re.findall(r'(\w+)=([^\s]+)', args_raw):
                    val: Any = kv[1]
                    if val.isdigit():
                        val = int(val)
                    elif val.replace(".", "").isdigit():
                        val = float(val)
                    args[kv[0]] = val
            calls.append(ToolCall(name=name, args=args))

        # 格式2：JSON 代码块
        for match in re.finditer(r'```tool_call\s*\n(.*?)\n```', text, re.DOTALL):
            try:
                data = json.loads(match.group(1))
                if isinstance(data, dict):
                    calls.append(ToolCall(
                        name=data.get("name", ""),
                        args=data.get("args", {}),
                    ))
            except json.JSONDecodeError:
                pass

        return [c for c in calls if c.name in self._tools]

    async def execute_call(self, call: ToolCall) -> ToolResult:
        """执行一个工具调用"""
        tool = self._tools.get(call.name)
        if not tool:
            return ToolResult(False, "", f"未知工具: {call.name}")
        try:
            return await tool.execute(**call.args)
        except Exception as e:
            logger.error(f"Tool {call.name} failed: {e}")
            return ToolResult(False, "", str(e))
