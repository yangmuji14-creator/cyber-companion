"""计算器工具 — 安全的数学表达式求值"""

import ast
import math
import operator

from .base import BaseTool, ToolResult


# 安全的操作符白名单
_ALLOWED_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

# 安全的函数白名单
_ALLOWED_FUNCS = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    "int": int,
    "float": float,
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "log10": math.log10,
    "ceil": math.ceil,
    "floor": math.floor,
    "pi": lambda: math.pi,
    "e": lambda: math.e,
}


def _safe_eval(expr: str) -> float:
    """安全求值数学表达式（仅允许白名单操作符和函数）

    Raises:
        ValueError: 表达式包含不允许的操作
    """
    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError as e:
        raise ValueError(f"表达式语法错误: {e}")

    def _eval(node):
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError(f"不支持的常量: {type(node.value).__name__}")
        elif isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in _ALLOWED_OPS:
                raise ValueError(f"不支持的操作符: {op_type.__name__}")
            left = _eval(node.left)
            right = _eval(node.right)
            return _ALLOWED_OPS[op_type](left, right)
        elif isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type not in _ALLOWED_OPS:
                raise ValueError(f"不支持的操作符: {op_type.__name__}")
            return _ALLOWED_OPS[op_type](_eval(node.operand))
        elif isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("不支持的函数调用")
            func_name = node.func.id
            if func_name not in _ALLOWED_FUNCS:
                raise ValueError(f"不支持的函数: {func_name}")
            args = [_eval(arg) for arg in node.args]
            func = _ALLOWED_FUNCS[func_name]
            # 常量函数（如 pi, e）不接受参数
            if func_name in ("pi", "e"):
                return func()
            return func(*args)
        elif isinstance(node, ast.Expression):
            return _eval(node.body)
        else:
            raise ValueError(f"不支持的表达式: {type(node).__name__}")

    return _eval(tree)


class CalculatorTool(BaseTool):
    """安全数学计算器"""

    @property
    def name(self) -> str:
        return "calculator"

    @property
    def description(self) -> str:
        return "执行数学计算，支持加减乘除、幂运算、三角函数、对数等"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "数学表达式，如 '2 + 2', 'sqrt(144)', 'sin(30) * pi / 180'",
                }
            },
            "required": ["expression"],
        }

    async def execute(self, expression: str) -> ToolResult:
        try:
            result = _safe_eval(expression)
            # 处理浮点数显示
            if isinstance(result, float):
                if result == int(result) and abs(result) < 1e15:
                    output = str(int(result))
                else:
                    output = f"{result:.6f}".rstrip("0").rstrip(".")
            else:
                output = str(result)

            return ToolResult(
                success=True,
                output=output,
                data={"expression": expression, "result": result},
            )
        except (ValueError, ZeroDivisionError) as e:
            return ToolResult(
                success=False,
                output=f"计算错误：{e}",
                error=str(e),
            )
