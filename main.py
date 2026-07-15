"""Cyber Girlfriend — 赛博伴侣

集成情绪状态机、人格引擎、工具调用、向量记忆等完整功能。

最简单的用法：
    python main.py 启动
    
或者用命令行：
    python main.py setup     — 首次运行，配置模型+人设
    python main.py           — 启动聊天（自动检测微信配置）
    python main.py wechat    — 首次配置微信
    python main.py import-skill <路径>  — 导入 ex-skill 人设文件
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
from loguru import logger

load_dotenv()

from core.config import ROOT, CONFIG_DIR, DATA_DIR, load_advanced
from core.app import AppComponents, create_components

# 日志
logger.remove()
logger.add(sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{level:8}</level> | {message}")
logger.add("logs/app.log", rotation="10 MB", retention="7 days", level="DEBUG")

ADVANCED = load_advanced()


# ========== 依赖检查 ==========

DEPENDENCIES = [
    ("dotenv", "python-dotenv"),
    ("loguru", "loguru"),
    ("pydantic", "pydantic"),
    ("litellm", "litellm"),
    ("numpy", "numpy"),
]


def _check_dependencies() -> bool:
    """启动前检查关键依赖是否已安装，缺失则给出友好提示"""
    missing = []
    for mod_name, pkg_name in DEPENDENCIES:
        try:
            __import__(mod_name)
        except ImportError:
            missing.append(pkg_name)

    if missing:
        print()
        print("=" * 50)
        print("  ❌ 缺少依赖包")
        print("=" * 50)
        print()
        print(f"  请先安装依赖：")
        print()
        print(f"    python install.py")
        print()
        if len(missing) <= 3:
            print(f"  缺失：{'、'.join(missing)}")
        print()
        input("  按回车键退出...")
        return False
    return True


# ========== 微信配置检测 ==========

def _has_wechat_config() -> bool:
    """检查是否已配置微信且允许自动启动"""
    credentials_file = ROOT / "data" / "credentials" / "wechat.json"
    if not credentials_file.exists():
        return False

    # 检查 settings.json 中的 auto_start 配置（默认允许自启）
    settings_path = CONFIG_DIR / "settings.json"
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            adapters = settings.get("advanced", {}).get("adapters", {})
            wechat = adapters.get("wechat", {})
            # auto_start 未设置时默认允许，兼容旧版无此配置的情况
            if wechat.get("auto_start") is False:
                return False
        except Exception:
            pass

    return True


# ========== CLI 入口 ==========

def _ensure_venv():
    """自动检测并使用 .venv 虚拟环境"""
    if sys.prefix != sys.base_prefix:
        return  # 已在 venv 中

    venv_dir = ROOT / ".venv"
    if not venv_dir.exists():
        return  # 没有 .venv，用系统 Python

    if sys.platform == "win32":
        venv_python = venv_dir / "Scripts" / "python.exe"
    else:
        venv_python = venv_dir / "bin" / "python"

    if not venv_python.exists():
        return

    # 用 venv 的 Python 重新执行
    print(f"\n  🔄 自动切换到虚拟环境...\n")
    os.execv(str(venv_python), [str(venv_python)] + sys.argv)


def main():
    import argparse

    # 自动检测并使用 .venv
    _ensure_venv()

    parser = argparse.ArgumentParser(description="Cyber Girlfriend")
    parser.add_argument(
        "command", nargs="?", default="run",
        choices=["setup", "run", "web", "wechat", "import-skill", "import-chat"],
        help="setup=配置向导, run=启动（默认）, web=网页端, wechat=配置微信, import-skill=导入人设, import-chat=导入聊天记录",
    )
    parser.add_argument(
        "path", nargs="?",
        help="import-skill 或 import-chat 时的文件路径",
    )
    parser.add_argument(
        "--name", "-n", default="",
        help="import-chat 时目标发言者的名字",
    )
    args = parser.parse_args()

    if args.command == "setup":
        from setup_wizard import run_setup
        try:
            run_setup()
        except KeyboardInterrupt:
            print("\n\n  设置已取消\n")
        return

    if args.command == "web":
        _run_web()
        return

    if args.command == "wechat":
        _setup_wechat()
        return

    if args.command == "import-skill":
        _import_skill_cli(args.path)
        return

    if args.command == "import-chat":
        _import_chat_cli(args.path, args.name)
        return

    # ── run（默认） ──
    if not _check_dependencies():
        return

    if not (ROOT / ".env").exists():
        print("\n" + "=" * 40)
        print("  首次使用，请先运行设置向导")
        print("=" * 40)
        print("\n  命令: python main.py setup")
        print("\n  按回车键退出...")
        try:
            input()
        except (EOFError, OSError):
            pass
        return

    logger.info("Cyber Girlfriend 启动中...")
    app: AppComponents = create_components()

    # 智能启动：如果已配置微信，自动启动微信+CLI
    if _has_wechat_config():
        print("\n  检测到微信配置，同时启动微信 Bot + 本地聊天")
        print("  微信消息和本地消息都会由同一个 AI 处理")
        print("  按 Ctrl+C 退出\n")
        from core.app import run_with_adapters
        try:
            asyncio.run(run_with_adapters(app, ["wechat"]))
        except KeyboardInterrupt:
            print()
            logger.info("拜拜~")
    else:
        print("\n  本地聊天模式")
        print("  输入 /help 查看命令，输入 /quit 退出\n")
        try:
            asyncio.run(app.handler.run())
        except KeyboardInterrupt:
            print()
            logger.info("拜拜~")


# ========== 网页端 ==========

def _run_web():
    """启动网页端（对话 + 参数配置）"""
    if not _check_dependencies():
        return

    if not (ROOT / ".env").exists():
        print("\n" + "=" * 40)
        print("  首次使用，请先运行设置向导")
        print("=" * 40)
        print("\n  命令: python main.py setup")
        return

    try:
        import aiohttp  # noqa: F401
    except ImportError:
        print("\n  ❌ 网页端需要 aiohttp，请先安装：")
        print("    pip install aiohttp\n")
        return

    logger.info("网页端启动中...")
    app: AppComponents = create_components()

    from webui.server import run_web
    try:
        asyncio.run(run_web(app))
    except KeyboardInterrupt:
        print()
        logger.info("网页端已停止")


# ========== 微信配置 ==========

def _setup_wechat():
    """配置微信 — 委托给 setup_wechat.py 统一入口"""
    from setup_wechat import run_wechat_setup
    run_wechat_setup()


# ========== 导入 ex-skill 人设 ==========

def _import_skill_cli(path_arg: str | None):
    """独立的 ex-skill 人设导入命令（需要 LLM 已配置）"""
    from import_exskill import run_import
    run_import(path_arg)


# ========== 导入聊天记录 ==========

def _import_chat_cli(chat_path: str | None, target_name: str):
    """从聊天记录导入人设、风格和记忆"""
    import asyncio
    from import_chat import run_import

    if not chat_path:
        print("\n  用法: python main.py import-chat <聊天记录文件> --name <目标名字>")
        print('  示例: python main.py import-chat chat.txt --name 张三')
        return

    if not target_name:
        target_name = input("请输入目标发言者的名字: ").strip()
        if not target_name:
            print("  ❌ 必须指定目标名字")
            return

    try:
        asyncio.run(run_import(chat_path, target_name))
    except KeyboardInterrupt:
        print("\n\n  已取消\n")
    except Exception as e:
        print(f"\n  ❌ 导入失败: {e}")


if __name__ == "__main__":
    main()
