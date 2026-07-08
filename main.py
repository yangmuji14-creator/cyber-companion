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
    """检查是否已配置微信"""
    credentials_file = ROOT / "data" / "credentials" / "wechat.json"
    return credentials_file.exists()


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
        choices=["setup", "run", "wechat", "import-skill"],
        help="setup=配置向导, run=启动（默认）, wechat=配置微信, import-skill=导入人设",
    )
    parser.add_argument(
        "path", nargs="?",
        help="import-skill 时的文件路径",
    )
    args = parser.parse_args()

    if args.command == "setup":
        from setup_wizard import run_setup
        try:
            run_setup()
        except KeyboardInterrupt:
            print("\n\n  设置已取消\n")
        return

    if args.command == "wechat":
        _setup_wechat()
        return

    if args.command == "import-skill":
        _import_skill_cli(args.path)
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


# ========== 微信配置 ==========

def _setup_wechat():
    """配置微信"""
    print("\n" + "=" * 40)
    print("  微信配置向导")
    print("=" * 40)
    print("\n  1. 确保你已安装微信 ClawBot 插件")
    print("  2. 准备好微信手机客户端")
    print("\n  按回车键开始扫码登录...")
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        print("\n\n  已取消\n")
        return

    try:
        from adapters.wechat import WeChatAdapter
        from adapters.base import AdapterConfig
        import asyncio

        adapter = WeChatAdapter()
        asyncio.run(adapter.start())

        print("\n" + "=" * 40)
        print("  微信配置完成！")
        print("=" * 40)
        print("\n  以后运行 'python main.py' 会自动启动微信")
        print("\n  按回车键退出...")
        input()
    except Exception as e:
        print(f"\n  配置失败: {e}")
        print("\n  按回车键退出...")
        input()


# ========== 导入 ex-skill 人设 ==========

def _import_skill_cli(path_arg: str | None):
    """独立的 ex-skill 人设导入命令（需要 LLM 已配置）"""
    from import_exskill import run_import
    run_import(path_arg)


if __name__ == "__main__":
    main()
