"""Resolve runtime command aliases without coupling tools to one OS."""

from __future__ import annotations

import shutil
import sys


def _real_python() -> str | None:
    """在冻结(PyInstaller)环境里找到机器上真实的 Python, 供子进程启动 MCP 脚本。"""
    for candidate in ("python", "py"):
        found = shutil.which(candidate)
        if found:
            return found
    return None


def resolve_runtime_command(command: str) -> str:
    """Map portable interpreter aliases to the interpreter running the app."""
    normalized = (command or "").strip().lower()
    if normalized in {"python", "python3", "{python}"}:
        # PyInstaller 冻结环境里 sys.executable 是 CyberCompanion.exe 而非 Python 解释器,
        # 直接用它当 python 启动子进程会导致握手超时, 必须回退到机器上真实的 python。
        if getattr(sys, "frozen", False):
            return _real_python() or sys.executable
        return sys.executable
    return command

