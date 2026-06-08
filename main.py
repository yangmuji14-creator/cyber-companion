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


def test_memory():
    """测试记忆系统"""
    from core.memory import MemoryManager

    manager = MemoryManager(str(ROOT / "data"))

    test_user = "test_user"

    # 测试添加记忆
    logger.info("=== 测试记忆系统 ===")

    m1 = manager.add_memory(test_user, "我的生日是5月20日")
    m2 = manager.add_memory(test_user, "我喜欢吃火锅")
    m3 = manager.add_memory(test_user, "今天天气不错")  # 低重要度，应该被跳过
    m4 = manager.add_memory(test_user, "我住在北京市朝阳区")

    logger.info(f"添加记忆: m1={m1 is not None}, m2={m2 is not None}, m3={m3 is not None}, m4={m4 is not None}")

    # 测试检索
    memories = manager.get_memories(test_user)
    logger.info(f"用户 {test_user} 共有 {len(memories)} 条记忆:")
    for m in memories:
        logger.info(f"  [{m.level}⭐] {m.content}")

    # 测试搜索
    results = manager.search_memories(test_user, "生日")
    logger.info(f"搜索'生日': 找到 {len(results)} 条")

    # 测试上下文 prompt
    context = manager.get_context_prompt(test_user)
    logger.info(f"上下文 prompt:\n{context}")

    # 测试导出
    exported = manager.export_memories(test_user)
    logger.info(f"导出记忆: {len(exported)} 条")

    # 清理测试数据
    manager._storage.delete_all(test_user)
    logger.info("测试数据已清理")


async def chat_loop():
    """交互式聊天循环"""
    from core.llm import init_registry
    from core.memory import MemoryManager
    from core.persona import PersonaLoader, PromptBuilder

    # 初始化组件
    registry = init_registry(CONFIG_DIR / "settings.json")
    memory_mgr = MemoryManager(str(ROOT / "data"))
    persona_loader = PersonaLoader(CONFIG_DIR / "personas.json")

    if not registry.available_models:
        logger.error("没有可用的模型！请检查 .env 文件中的 API Key 配置")
        return

    llm = registry.get()
    persona = persona_loader.get("girlfriend_001")
    if not persona:
        logger.error("默认人设 'girlfriend_001' 不存在")
        return

    user_id = "local_user"
    logger.info(f"模型: {llm.model_name}")
    logger.info(f"人设: {persona.name} ({', '.join(persona.personality)})")
    logger.info("=" * 40)
    logger.info("开始聊天吧！输入 'quit' 退出")
    logger.info("=" * 40)

    messages: list[dict[str, str]] = []

    while True:
        try:
            user_input = input("\n你: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input or user_input.lower() == "quit":
            break

        # 添加用户消息
        messages.append({"role": "user", "content": user_input})

        # 构建 system prompt（人设 + 记忆上下文）
        memory_context = memory_mgr.get_context_prompt(user_id)
        system_prompt = PromptBuilder.build(persona, memory_context=memory_context)

        # 调用 LLM
        response = await llm.chat(messages=messages, system_prompt=system_prompt)

        # 添加助手回复到消息历史
        messages.append({"role": "assistant", "content": response.content})

        # 自动提取记忆
        memory_mgr.add_memory(user_id, user_input)

        print(f"\n{persona.name}: {response.content}")

        # 保持消息历史不要太长（最近 20 条）
        if len(messages) > 20:
            messages = messages[-20:]

    logger.info("聊天结束，拜拜~")


def main():
    """主入口"""
    logger.info("🎀 Cyber Girlfriend 启动中...")
    logger.info(f"项目目录: {ROOT}")

    # 检查 .env 是否存在
    env_file = ROOT / ".env"
    if not env_file.exists():
        logger.warning(".env 文件不存在，请复制 .env.example 为 .env 并填写 API Key")
        logger.info("cp .env.example .env")

    # 启动聊天
    asyncio.run(chat_loop())


if __name__ == "__main__":
    main()
