"""Build a platform-neutral portable bundle from a self-contained runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIRS = ("core", "adapters", "mcp_servers", "plugins", "tools", "webui")
APP_FILES = (
    "main.py", "setup_wizard.py", "setup_wechat.py", "import_chat.py",
    "import_exskill.py", ".env.example",
)
CONFIG_EXAMPLES = ("settings.example.json", "personas.example.json", "mcp_servers.example.json")


def _copy_tree(source: Path, target: Path) -> None:
    shutil.copytree(
        source, target, dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(
            "__pycache__", "*.pyc", ".pytest_cache", ".git",
            "__tests__", "*.test.js",
        ),
    )


def _runtime_platform(runtime_dir: Path, requested: str) -> str:
    if requested == "auto":
        if (runtime_dir / "python.exe").is_file():
            return "windows"
        if (runtime_dir / "bin" / "python").is_file():
            return "unix"
        raise ValueError("runtime-dir 缺少 python.exe 或 bin/python")
    expected = runtime_dir / ("python.exe" if requested == "windows" else "bin/python")
    if not expected.is_file():
        raise ValueError(f"{requested} runtime 缺少启动文件: {expected}")
    return requested


def build(
    runtime_dir: Path,
    output_dir: Path,
    version: str,
    target_platform: str = "auto",
) -> Path:
    runtime_dir = runtime_dir.resolve()
    if not runtime_dir.is_dir() or not any(runtime_dir.iterdir()):
        raise ValueError(f"runtime-dir 不存在或为空: {runtime_dir}")
    resolved_platform = _runtime_platform(runtime_dir, target_platform)

    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mu-build-") as temp:
        bundle = Path(temp) / "Mu"
        app = bundle / "app"
        runtime = bundle / "runtime"
        app.mkdir(parents=True)
        _copy_tree(runtime_dir, runtime)

        for directory in APP_DIRS:
            _copy_tree(ROOT / directory, app / directory)
        for filename in APP_FILES:
            source = ROOT / filename
            if source.exists():
                shutil.copy2(source, app / filename)
        (app / "config").mkdir()
        for filename in CONFIG_EXAMPLES:
            source = ROOT / "config" / filename
            if source.exists():
                shutil.copy2(source, app / "config" / filename)
        shutil.copy2(ROOT / "packaging" / "portable_launcher.py", app / "portable_launcher.py")

        (bundle / "userdata" / "config").mkdir(parents=True)
        (bundle / "userdata" / "data").mkdir()
        (bundle / "userdata" / "logs").mkdir()
        (bundle / "portable.json").write_text(
            json.dumps({
                "format": 1,
                "version": version,
                "target_platform": resolved_platform,
                "data_policy": "userdata",
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        shutil.copy2(ROOT / "packaging" / "start_windows.cmd", bundle / "启动慕.cmd")
        shutil.copy2(ROOT / "packaging" / "start_unix.sh", bundle / "start.sh")
        (bundle / "README.txt").write_text(
            "解压后双击“启动慕.cmd”。聊天记录和配置保存在 userdata 文件夹。\n",
            encoding="utf-8",
        )

        archive = output_dir.resolve() / f"Mu-{version}-portable.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for file in bundle.rglob("*"):
                if file.is_file():
                    zf.write(file, file.relative_to(bundle.parent))
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        archive.with_suffix(archive.suffix + ".sha256").write_text(
            f"{digest}  {archive.name}\n",
            encoding="ascii",
        )
        return archive


def main() -> int:
    parser = argparse.ArgumentParser(description="构建慕便携压缩包")
    parser.add_argument("--runtime-dir", required=True, type=Path, help="自包含运行时目录")
    parser.add_argument("--output", default="dist", type=Path)
    parser.add_argument("--version", default="4.3.0")
    parser.add_argument(
        "--target-platform",
        choices=("auto", "windows", "linux", "macos"),
        default="auto",
        help="校验运行时布局并写入发行清单",
    )
    args = parser.parse_args()
    archive = build(args.runtime_dir, args.output, args.version, args.target_platform)
    print(f"便携包已生成: {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
