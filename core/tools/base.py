"""工具调用基类和注册中心

提供 OpenAI/Anthropic 兼容的 function calling 接口。
工具通过 ToolRegistry 统一注册和管理。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    """工具执行结果"""
    success: bool
    output: str
    error: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


class BaseTool(ABC):
    """工具基类

    每个工具需要定义：
    - name: 工具名称（用于 LLM 识别）
    - description: 工具描述（用于 LLM 选择）
    - parameters: OpenAI function calling 格式的参数 schema

    子类实现 execute() 方法。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        ...

    @property
    def parameters(self) -> dict[str, Any]:
        """OpenAI function calling 格式的参数 schema

        默认返回无参数 schema，子类可覆盖。
        """
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """执行工具

        Args:
            **kwargs: 从 LLM 解析的参数

        Returns:
            ToolResult 包含执行结果
        """
        ...

    def to_function_spec(self) -> dict[str, Any]:
        """生成 OpenAI function calling 格式的 tool 定义"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


# Tool 别名（兼容 builtin.py 导入）
Tool = BaseTool


@dataclass
class ToolCall:
    """解析后的工具调用"""
    name: str
    params: dict[str, str] = field(default_factory=dict)
    raw_text: str = ""


class ToolRegistry:
    """工具注册中心

    管理所有可用工具，按名称索引。
    """

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """注册一个工具"""
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        """按名称获取工具"""
        return self._tools.get(name)

    def list_tools(self) -> list[BaseTool]:
        """列出所有已注册的工具"""
        return list(self._tools.values())

    def get_function_specs(self) -> list[dict[str, Any]]:
        """获取所有工具的 function calling 格式定义"""
        return [t.to_function_spec() for t in self._tools.values()]

    def get_prompt_block(self) -> str:
        """生成工具描述 prompt 块"""
        if not self._tools:
            return ""
        lines = ["可用工具："]
        for tool in self._tools.values():
            lines.append(f"- {tool.name}: {tool.description}")
        return "\n".join(lines)

    def parse_calls(self, text: str) -> list[ToolCall]:
        """从文本中解析工具调用

        支持格式：
        - /call 工具名(参数名="值")
        - /call 工具名 参数名="值"
        - /call 工具名
        """
        import re
        results = []
        # 匹配 /call 工具名(参数名="值", ...)
        pattern = re.compile(r'/call\s+(\w+)(?:\(([^)]*)\))?')
        for match in pattern.finditer(text):
            name = match.group(1)
            if name not in self._tools:
                continue
            params = {}
            params_str = match.group(2) or ""
            if params_str.strip():
                for param_match in re.finditer(r'(\w+)\s*=\s*["\']([^"\']*)["\']', params_str):
                    params[param_match.group(1)] = param_match.group(2)
            results.append(ToolCall(name=name, params=params, raw_text=match.group(0)))
        return results

    @property
    def available(self) -> bool:
        """是否有工具可用"""
        return len(self._tools) > 0

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())
