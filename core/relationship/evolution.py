"""关系进化系统 — 关系阶段影响行为画像

将关系亲密度（0-100）映射为行为阶段，每个阶段有不同的：
- 说话风格
- 主动程度
- 昵称使用频率
- 情感表达强度
- 记忆引用频率

通过 behavior_profile 动态驱动 PromptBuilder，禁止写死 Prompt。
"""

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BehaviorProfile:
    """行为画像 — 关系阶段驱动的行为参数

    所有字段 0.0~1.0，越大表示该特征越明显。
    """
    # 说话风格
    formality: float = 0.8        # 正式程度（高→礼貌克制，低→随意亲昵）
    warmth: float = 0.3           # 温暖程度（高→热情，低→冷淡）
    verbosity: float = 0.4        # 话多程度（高→长篇，低→简短）

    # 主动性
    initiative: float = 0.2       # 主动程度（高→经常主动找话题）
    question_frequency: float = 0.3  # 提问频率（高→经常反问用户）

    # 情感表达
    emotional_intensity: float = 0.3   # 情感表达强度
    emoji_density: float = 0.3         # emoji 使用密度
    nickname_frequency: float = 0.1    # 昵称使用频率

    # 记忆引用
    memory_reference_rate: float = 0.2  # 引用旧记忆的频率
    follow_up_rate: float = 0.1        # 追问过去话题的频率

    def to_prompt_instructions(self) -> str:
        """生成行为指令文本，注入 PromptBuilder"""
        lines = ["【关系阶段行为指导】"]

        # 正式程度
        if self.formality >= 0.7:
            lines.append("- 说话保持礼貌，用敬语")
        elif self.formality >= 0.4:
            lines.append("- 说话自然随和，偶尔用敬语")
        else:
            lines.append("- 说话随意亲昵，不用敬语")

        # 温暖程度
        if self.warmth >= 0.7:
            lines.append("- 语气温暖热情，多表达关心")
        elif self.warmth >= 0.4:
            lines.append("- 语气温和友善")
        else:
            lines.append("- 语气平淡，保持距离感")

        # 主动程度
        if self.initiative >= 0.6:
            lines.append("- 可以主动找话题，多发起对话")
        elif self.initiative >= 0.3:
            lines.append("- 适当主动，偶尔发起话题")
        else:
            lines.append("- 等对方先开口，不主动")

        # 情感表达
        if self.emotional_intensity >= 0.6:
            lines.append("- 可以充分表达情感和感受")
        elif self.emotional_intensity >= 0.3:
            lines.append("- 适度表达情感")
        else:
            lines.append("- 克制情感表达")

        # emoji
        if self.emoji_density >= 0.6:
            lines.append("- 多使用 emoji 表达情绪")
        elif self.emoji_density >= 0.3:
            lines.append("- 适当使用 emoji")
        else:
            lines.append("- 少用 emoji")

        # 昵称
        if self.nickname_frequency >= 0.5:
            lines.append("- 可以称呼昵称")
        else:
            lines.append("- 用正常称呼")

        # 记忆引用
        if self.memory_reference_rate >= 0.5:
            lines.append("- 经常提起你们之间的共同回忆")
        elif self.memory_reference_rate >= 0.2:
            lines.append("- 偶尔提起过去的聊天内容")
        else:
            lines.append("- 不主动提起过去的事")

        return "\n".join(lines)


class RelationshipEvolution:
    """关系进化引擎

    将亲密度 level 映射为行为画像。
    关系阶段：
    - 陌生 0~20：礼貌、谨慎
    - 熟悉 20~50：主动提问、记住近期话题
    - 亲近 50~80：主动提及旧记忆、更多情感表达
    - 深度关系 80~100：高主动性、昵称增加、更强连续性
    """

    @staticmethod
    def get_stage(level: int) -> str:
        """获取关系阶段名称"""
        if level >= 80:
            return "deep"
        elif level >= 50:
            return "close"
        elif level >= 20:
            return "familiar"
        else:
            return "stranger"

    @staticmethod
    def get_stage_label(level: int) -> str:
        """获取关系阶段的中文标签"""
        labels = {
            "deep": "深度关系",
            "close": "亲近",
            "familiar": "熟悉",
            "stranger": "陌生",
        }
        return labels.get(RelationshipEvolution.get_stage(level), "陌生")

    @staticmethod
    def get_profile(level: int) -> BehaviorProfile:
        """根据亲密度生成行为画像"""
        # 归一化 level 到 0.0~1.0
        t = max(0.0, min(1.0, level / 100.0))

        # 使用非线性映射让中后期变化更明显
        # 曲线：在 0-20 阶段变化慢，20-80 快速变化，80-100 趋平
        if level < 20:
            t_smooth = t * 0.3  # 陌生阶段
        elif level < 50:
            t_smooth = 0.06 + (t - 0.2) * 1.5  # 熟悉阶段
        elif level < 80:
            t_smooth = 0.5 + (t - 0.5) * 1.3  # 亲近阶段
        else:
            t_smooth = 0.8 + (t - 0.8) * 0.8  # 深度关系

        t_smooth = max(0.0, min(1.0, t_smooth))

        return BehaviorProfile(
            # 正式度随关系递减
            formality=max(0.1, 1.0 - t_smooth * 0.8),
            # 温暖度递增
            warmth=0.3 + t_smooth * 0.6,
            # 话多程度递增
            verbosity=0.3 + t_smooth * 0.5,
            # 主动性递增
            initiative=0.2 + t_smooth * 0.7,
            # 提问频率先增后稳
            question_frequency=0.2 + min(t_smooth, 0.6) * 0.6,
            # 情感表达强度递增
            emotional_intensity=0.2 + t_smooth * 0.7,
            # emoji 密度递增
            emoji_density=0.2 + t_smooth * 0.5,
            # 昵称频率：中后期快速增加
            nickname_frequency=max(0.0, (t_smooth - 0.3) * 1.2),
            # 记忆引用递增
            memory_reference_rate=0.1 + t_smooth * 0.7,
            # 追问频率递增
            follow_up_rate=0.05 + t_smooth * 0.6,
        )

    @staticmethod
    def get_stage_description(level: int) -> str:
        """生成关系阶段描述文本"""
        stage = RelationshipEvolution.get_stage(level)
        descriptions = {
            "stranger": "你们刚认识不久，还在互相了解的阶段。彼此礼貌而谨慎，对话保持着适当的距离。",
            "familiar": "你们已经熟悉起来了，开始记住对方的事情，会主动问候和关心。对话自然流畅。",
            "close": "你们关系很亲密，会分享日常，表达情感，偶尔撒娇。已经建立了属于你们的默契。",
            "deep": "你们是彼此很重要的人。无需太多言语就能理解对方，情感深厚而稳定。会主动维系关系。",
        }
        return descriptions.get(stage, "")

    @staticmethod
    def get_nickname_style(level: int, persona=None) -> str:
        """根据关系阶段推荐昵称风格"""
        stage = RelationshipEvolution.get_stage(level)
        if persona and persona.nickname_for_user:
            return persona.nickname_for_user
        nicknames = {
            "stranger": "你",
            "familiar": "你/你的名字",
            "close": "亲爱的/宝贝/专属昵称",
            "deep": "宝宝/老公/老婆/亲昵称呼",
        }
        return nicknames.get(stage, "你")
