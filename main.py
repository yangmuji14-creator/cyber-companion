"""Cyber Girlfriend — 赛博女友

最简单的用法：
    python main.py 启动
    
或者用命令行：
    python main.py setup   — 首次运行，配置模型
    python main.py         — 启动聊天（自动检测微信配置）
    python main.py wechat  — 首次配置微信
"""

import asyncio
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
from loguru import logger

load_dotenv()

from core.config import ROOT
from core.app import create_components, AppComponents


# ========== 日志初始化 ==========

logger.remove()
logger.add(sys.stderr, level="INFO",
           format="<green>{time:HH:mm:ss}</green> | <level>{level:8}</level> | {message}")
logger.add("logs/app.log", rotation="10 MB", retention="7 days", level="DEBUG")


# ========== 微信配置检测 ==========

def _has_wechat_config() -> bool:
    """检查是否已配置微信"""
    credentials_file = ROOT / "data" / "credentials" / "wechat.json"
    return credentials_file.exists()


# ========== CLI 入口 ==========

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Cyber Girlfriend")
    parser.add_argument(
        "command", nargs="?", default="run",
        choices=["setup", "run", "wechat"],
        help="setup=首次配置, run=启动聊天（默认）, wechat=配置微信",
    )
    args = parser.parse_args()

    if args.command == "setup":
        from setup import run_setup
        run_setup()
        return

    if args.command == "wechat":
        _setup_wechat()
        return

    if not (ROOT / ".env").exists():
        print("\n" + "="*40)
        print("  首次使用，请先运行设置向导")
        print("="*40)
        print("\n  命令: python main.py setup")
        print("\n  按回车键退出...")
        input()
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


def _setup_wechat():
    """配置微信"""
    print("\n" + "="*40)
    print("  微信配置向导")
    print("="*40)
    print("\n  1. 确保你已安装微信 ClawBot 插件")
    print("  2. 准备好微信手机客户端")
    print("\n  按回车键开始扫码登录...")
    input()

    try:
        from adapters.wechat import WeChatAdapter
        from adapters.base import AdapterConfig
        import asyncio

        adapter = WeChatAdapter()
        asyncio.run(adapter.start())

        print("\n" + "="*40)
        print("  微信配置完成！")
        print("="*40)
        print("\n  以后运行 'python main.py' 会自动启动微信")
        print("\n  按回车键退出...")
        input()
    except Exception as e:
        print(f"\n  配置失败: {e}")
        print("\n  按回车键退出...")
        input()


if __name__ == "__main__":
    main()
