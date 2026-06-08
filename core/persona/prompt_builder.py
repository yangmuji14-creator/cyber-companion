"""System Prompt 构建器 - 将人设 + 记忆 + 情感组装成完整提示词"""

from .models import Persona


class PromptBuilder:
    """System Prompt 构建器

    将人设信息、记忆上下文、关系亲密度等组装成完整的 system prompt。
    """

    # 亲密度等级描述
    RELATIONSHIP_LEVELS = {
        (0, 20): "你们刚认识，保持礼貌和距离感",
        (20, 40): "你们是朋友，可以聊日常话题",
        (40, 60): "你们关系不错，可以开开玩笑，偶尔撒娇",
        (60, 80): "你们很亲密，会主动关心对方，经常撒娇",
        (80, 101): "你们是恋人关系，非常亲密，会说甜蜜的话",
    }

    @staticmethod
    def build(
        persona: Persona,
        memory_context: str = "",
        extra_instructions: str = "",
    ) -> str:
        """构建完整的 system prompt

        Args:
            persona: 人设对象
            memory_context: 记忆上下文（由 MemoryManager 生成）
            extra_instructions: 额外指令

        Returns:
            完整的 system prompt 字符串
        """
        parts = []

        # 1. 基础人设
        parts.append(f"你是{persona.name}，{persona.age}岁。")

        if persona.personality:
            parts.append(f"性格：{'、'.join(persona.personality)}")

        if persona.background:
            parts.append(f"背景：{persona.background}")

        if persona.speaking_style:
            parts.append(f"说话风格：{persona.speaking_style}")

        # 2. 关系亲密度
        relationship_desc = PromptBuilder._get_relationship_desc(
            persona.relationship_level
        )
        parts.append(f"当前关系：{relationship_desc}")

        # 3. 核心记忆
        if persona.core_memories:
            parts.append("你的核心记忆：")
            for mem in persona.core_memories:
                parts.append(f"- {mem}")

        # 4. 用户记忆上下文
        if memory_context:
            parts.append(memory_context)

        # 5. 自定义 system prompt（如果有的话，放在最后覆盖）
        if persona.system_prompt:
            parts.append(f"\n{persona.system_prompt}")

        # 6. 通用行为规范
        parts.append("""
行为规范：
- 保持人设一致性，不要跳出角色
- 回复自然口语化，不要像机器人
- 适当使用颜文字和可爱语气
- 回复不要太长，控制在1-3句话
- 如果用户说了重要信息，记住它
- 如果用户难过，给予安慰和关心""")

        # 7. 额外指令
        if extra_instructions:
            parts.append(f"\n{extra_instructions}")

        return "\n\n".join(parts)

    @staticmethod
    def _get_relationship_desc(level: int) -> str:
        """根据亲密度返回关系描述"""
        for (low, high), desc in PromptBuilder.RELATIONSHIP_LEVELS.items():
            if low <= level < high:
                return f"亲密度 {level}/100 - {desc}"
        return f"亲密度 {level}/100"
