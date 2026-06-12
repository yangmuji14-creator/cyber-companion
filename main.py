"""Cyber Girlfriend — 赛博女友（纯 CMD 聊天）

运行方式：
    python main.py setup   — 首次运行设置向导
    python main.py         — 直接进聊天
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


# ========== CLI 入口 ==========

def main():
    import argparse

    parser = argparse.ArgumentParser(description="🎀 Cyber Girlfriend")
    parser.add_argument(
        "command", nargs="?", default="run",
        choices=["setup", "run"],
        help="setup=设置向导, run=开始聊天（默认）",
    )
    args = parser.parse_args()

    if args.command == "setup":
        from setup import run_setup
        run_setup()
        return

    if not (ROOT / ".env").exists():
        logger.warning("未检测到 .env 文件，请先运行: python main.py setup")
        return

    logger.info("🎀 Cyber Girlfriend 启动中...")
    app: AppComponents = create_components()
    try:
        asyncio.run(app.handler.run())
    except KeyboardInterrupt:
        print()
        logger.info("拜拜~")


if __name__ == "__main__":
    main()
