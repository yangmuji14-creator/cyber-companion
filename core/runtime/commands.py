"""Resolve runtime command aliases without coupling tools to one OS."""

from __future__ import annotations

import sys


def resolve_runtime_command(command: str) -> str:
    """Map portable interpreter aliases to the interpreter running the app."""
    normalized = (command or "").strip().lower()
    if normalized in {"python", "python3", "{python}"}:
        return sys.executable
    return command

