"""Cold-start a built portable bundle and verify its public health endpoint."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import zipfile
from pathlib import Path


def smoke_test(archive: Path, extract_dir: Path, port: int = 8765) -> None:
    archive = archive.resolve()
    extract_dir = extract_dir.resolve()
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(extract_dir)

    root = extract_dir / "Mu"
    runtime_python = root / "runtime" / ("python.exe" if os.name == "nt" else "bin/python")
    app = root / "app"
    if not runtime_python.is_file():
        raise RuntimeError(f"便携运行时入口不存在: {runtime_python}")

    env = os.environ.copy()
    env.update(
        {
            "CC_PORTABLE": "1",
            "CC_PORTABLE_ROOT": str(root),
            "CC_RESOURCE_DIR": str(app),
            "CC_WEB_PORT": str(port),
            "CC_NO_BROWSER": "1",
            "CC_STARTUP_CHECK_ONLY": "1",
            "PYTHONUTF8": "1",
        }
    )
    command = [str(runtime_python), str(app / "portable_launcher.py")]
    if os.name == "nt":
        command = ["cmd.exe", "/d", "/c", str(root / "启动慕.cmd")]
    process = subprocess.run(
        command,
        cwd=app,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=90,
    )
    if process.returncode:
        output = (process.stdout or "") + (process.stderr or "")
        raise RuntimeError(f"便携启动器自检失败 ({process.returncode}):\n{output[-4000:]}")
    print(f"portable launcher smoke test ok: http://127.0.0.1:{port}/api/health")


def main() -> int:
    parser = argparse.ArgumentParser(description="验证便携压缩包可在空目录中冷启动")
    parser.add_argument("archive", type=Path)
    parser.add_argument("--extract-dir", type=Path, default=Path("build/portable-smoke"))
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    smoke_test(args.archive, args.extract_dir, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
