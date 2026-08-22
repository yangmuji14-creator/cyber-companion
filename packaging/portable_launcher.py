"""Portable bundle launcher shared by Windows, Linux and macOS wrappers."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path


def _bundle_root() -> tuple[Path, Path]:
    app_dir = Path(__file__).resolve().parent
    return (app_dir.parent, app_dir) if app_dir.name == "app" else (app_dir, app_dir)


def _wait_for_server(url: str, process: subprocess.Popen, timeout: float = 45.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(f"{url}/api/health", timeout=1.5) as response:
                if response.status == 200:
                    return True
        except Exception:
            time.sleep(0.25)
    return False


def _available_port(host: str, preferred: int = 8000) -> int:
    """Choose a local port without hard-coding one platform's tooling."""
    for port in range(preferred, preferred + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind((host, port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"本地端口 {preferred}-{preferred + 19} 均被占用")


def _stop(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> int:
    bundle_dir, app_dir = _bundle_root()
    env = os.environ.copy()
    env.update({
        "CC_PORTABLE": "1",
        "CC_PORTABLE_ROOT": str(bundle_dir),
        "CC_RESOURCE_DIR": str(app_dir),
        "PYTHONUTF8": "1",
    })
    host = env.get("CC_WEB_HOST", "127.0.0.1")
    configured_port = env.get("CC_WEB_PORT", "").strip()
    try:
        port = int(configured_port) if configured_port else _available_port(host)
    except ValueError:
        print("CC_WEB_PORT 必须是有效端口号", file=sys.stderr)
        return 2
    env["CC_WEB_HOST"] = host
    env["CC_WEB_PORT"] = str(port)
    url = f"http://127.0.0.1:{port}"
    main_file = app_dir / "main.py"
    if not main_file.exists():
        print(f"应用文件不存在: {main_file}", file=sys.stderr)
        return 2

    # Keep child stdout/stderr attached to the launch window by default.
    flags = (
        getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if os.name == "nt" and env.get("CC_HIDE_LOGS", "").lower() in {"1", "true", "yes", "on"}
        else 0
    )
    process = subprocess.Popen(
        [sys.executable, str(main_file), "web"],
        cwd=str(app_dir), env=env, creationflags=flags,
    )
    if not _wait_for_server(url, process):
        print("网页服务启动失败，请查看 userdata/logs/app.log", file=sys.stderr)
        _stop(process)
        return process.returncode or 1
    print(f"慕已启动: {url}")
    if env.get("CC_STARTUP_CHECK_ONLY", "").lower() in {"1", "true", "yes", "on"}:
        _stop(process)
        return 0
    if env.get("CC_NO_BROWSER", "").lower() not in {"1", "true", "yes", "on"}:
        webbrowser.open(url)
    return process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
