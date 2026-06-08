"""Cyber Girlfriend - 赛博女友主入口"""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

# 加载环境变量
load_dotenv()

# 配置日志
logger.remove()
logger.add(sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{level:8}</level> | {message}")
logger.add("logs/app.log", rotation="10 MB", retention="7 days", level="DEBUG")

# 项目根目录
ROOT = Path(__file__).parent
CONFIG_DIR = ROOT / "config"


async def test_llm():
    """测试 LLM 接入是否正常"""
    from core.llm import init_registry

    registry = init_registry(CONFIG_DIR / "settings.json")

    logger.info(f"可用模型: {registry.available_models}")
    logger.info(f"默认模型: {registry.default_model}")

    if not registry.available_models:
        logger.error("没有可用的模型！请检查 .env 文件中的 API Key 配置")
        return

    llm = registry.get()
    logger.info(f"测试模型: {llm.model_name}")

    response = await llm.chat(
        messages=[{"role": "user", "content": "你好呀，介绍一下你自己~"}],
        system_prompt="你是小雨，一个22岁的大学生，性格温柔活泼，偶尔傲娇。请用可爱自然的语气回复。",
    )

    logger.info(f"回复内容:\n{response.content}")
    logger.info(f"Token 用量: {response.usage}")


def main():
    """主入口"""
    logger.info("🎀 Cyber Girlfriend 启动中...")
    logger.info(f"项目目录: {ROOT}")

    # 检查 .env 是否存在
    env_file = ROOT / ".env"
    if not env_file.exists():
        logger.warning(".env 文件不存在，请复制 .env.example 为 .env 并填写 API Key")
        logger.info("cp .env.example .env")

    # 运行 LLM 测试
    asyncio.run(test_llm())


if __name__ == "__main__":
    main()
