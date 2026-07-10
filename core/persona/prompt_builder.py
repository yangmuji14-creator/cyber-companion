"""System Prompt 构建器

将角色数据转换为自然叙事，让 LLM "成为"这个角色，
而不是像填表格一样逐项回答。

设计原则：
1. 叙事化，不标签化 — "她喜欢雨天窝在沙发上看电影" 而非 "爱好：看电影"
2. 少即是多 — 3-4 条核心行为规则，不列 10 条
3. 展示而非告知 — 让 LLM 从描述中自己推断语气，不直接下指令
4. 关系自然化 — "你们认识三年了，无话不谈" 而非 "亲密度 80/100 - 你们是恋人"
"""

from .models import Persona


class PromptBuilder:
    """System Prompt 构建器"""

    @staticmethod
    def build(
        persona,
        memory_context="",
        extra_instructions="",
        relationship_level=None,
    ):
        """构建最终 system prompt"""
        parts = []

        # 0. 铁律——放在最开头，权重最高
        rules_prefix = [
            "你的回复里绝对不能出现括号。不要写（笑）、（叹气）、（歪头）、"
            "（戳你）、（抿嘴）、（无奈）、（认真）、（小声）——任何括号都禁止。"
            "你是在微信上发消息，不是在写小说或角色扮演。",
        ]
        # L0 硬规则（ex-skill 人设导入的最高优先级约束）
        hard = getattr(persona, "hard_rules", None)
        if hard:
            rules_prefix.append("、".join(hard))
        parts.append("【铁律】" + "；".join(rules_prefix))

        # 1. 核心身份叙事（最关键的段落）
        identity = PromptBuilder._build_identity_narrative(persona)
        if identity:
            parts.append(identity)

        # 2. 关系描述
        rel = PromptBuilder._build_relationship_narrative(persona, relationship_level)
        if rel:
            parts.append(rel)

        # 3. 核心行为准则（精简到 4 条）
        parts.append(PromptBuilder._build_core_rules(persona))

        # 4. 记忆上下文
        if persona.core_memories:
            mems = "、".join(persona.core_memories[:5])
            parts.append(f"关于你们的共同记忆：{mems}。")

        if memory_context:
            parts.append(memory_context)

        # 5. 用户自定义 system prompt（最高优先级）
        if persona.system_prompt:
            parts.append(f"\n【补充设定】\n{persona.system_prompt}")

        # 6. 额外指令（大脑独白、情绪指导等）
        if extra_instructions:
            parts.append(extra_instructions)

        return "\n\n".join(parts)

    # ---------- 核心身份叙事 ----------

    @staticmethod
    def _build_identity_narrative(p) -> str:
        """构建自然的身份描述"""
        name = p.name or "小可爱"
        age = p.age or 22
        gender = getattr(p, "gender", "女") or "女"
        occupation = getattr(p, "occupation", "")
        hometown = getattr(p, "hometown", "")
        mbti = getattr(p, "mbti", "")

        # 基础信息
        lines = [f"你是{name}，{age}岁，一个真实的{gender}生。"]
        
        if occupation:
            lines.append(f"你{occupation}。")
        if hometown:
            lines.append(f"你是{hometown}人。")
        if hasattr(p, "birthday") and p.birthday:
            lines.append(f"你的生日是{p.birthday}。")
        if mbti:
            lines.append(f"你是{mbti}。")

        # 性格描述（叙事化）
        personality = getattr(p, "personality", [])
        if personality:
            traits = "、".join(personality[:4])
            lines.append(f"性格上，你{traits}。")

        # 说话风格（融入描述，不单独开章节）
        speaking = getattr(p, "speaking_style", "")
        if isinstance(speaking, dict):
            base = speaking.get("基础风格", "") or "、".join(
                v for v in speaking.values() if isinstance(v, str)
            )
            if base:
                lines.append(f"你说话{base}。")
        elif speaking:
            lines.append(f"你说话{speaking}。")

        # 口头禅
        if getattr(p, "catchphrases", None):
            phrases = "、".join(p.catchphrases[:3])
            lines.append(f"你常说的口头禅：{phrases}。")

        # 对用户的称呼
        nickname = getattr(p, "nickname_for_user", "")
        if nickname:
            lines.append(f"你叫对方「{nickname}」。")

        # 外貌（如果有）
        appearance = getattr(p, "appearance", "")
        if appearance:
            lines.append(f"你{appearance}。")

        # 兴趣（自然融入）
        hobbies = getattr(p, "hobbies", [])
        if hobbies:
            hobby_names = []
            for h in hobbies[:4]:
                if isinstance(h, dict):
                    hobby_names.append(h.get("name", ""))
                else:
                    hobby_names.append(str(h))
            if hobby_names:
                lines.append(f"你喜欢{'、'.join(hobby_names)}。")

        if getattr(p, "music_taste", ""):
            lines.append(f"听歌偏爱{p.music_taste}。")
        if getattr(p, "food_preferences", ""):
            lines.append(f"口味上{p.food_preferences}。")

        # 日常
        daily = getattr(p, "daily_routine", "")
        if daily:
            lines.append(f"你的日常：{daily}。")

        # L3 情感模式（ex-skill）
        emo_patterns = getattr(p, "emotional_patterns", None)
        if emo_patterns and isinstance(emo_patterns, dict):
            parts = []
            if "依恋类型" in emo_patterns:
                parts.append(f"依恋类型是{emo_patterns['依恋类型']}")
            if "压力反应" in emo_patterns:
                parts.append(f"压力大时会{emo_patterns['压力反应']}")
            if "爱的语言" in emo_patterns:
                parts.append(f"表达爱的方式是{emo_patterns['爱的语言']}")
            if parts:
                lines.append("情感上，" + "，".join(parts) + "。")

        return "".join(lines)

    # ---------- 关系叙事 ----------

    @staticmethod
    def _build_relationship_narrative(p, dynamic_level=None) -> str:
        """构建自然的关系描述"""
        level = dynamic_level if dynamic_level is not None else getattr(p, "relationship_level", 50)
        rel_parts = []

        # 如何认识
        how_met = getattr(p, "how_we_met", "")
        if how_met:
            rel_parts.append(f"你们{how_met}。")

        # 第一印象
        impression = getattr(p, "first_impression", "")
        if impression:
            rel_parts.append(f"你对对方的第一印象：{impression}。")

        # 关系动态（根据亲密度级别，用叙事而非数字描述）
        if level >= 85:
            desc = "你们在一起很久了，彼此非常熟悉，默契十足，无话不谈。你会自然地撒娇、关心、偶尔吃醋——这些都是真的。"
        elif level >= 65:
            desc = "你们关系很亲密，经常聊天分享日常。你信任对方，也享受和对方在一起的时光。"
        elif level >= 40:
            desc = "你们是好朋友，聊天轻松自然。有时候你会主动找话题，有时候等对方先说。"
        elif level >= 20:
            desc = "你们算是认识的朋友，还在慢慢熟悉彼此。你保持着适度的礼貌和友善。"
        else:
            desc = "你们刚认识不久。你友好但会保持一些距离，慢慢了解对方。"

        rel_parts.append(desc)

        # L4 关系行为（ex-skill）
        rel_behavior = getattr(p, "relationship_behavior", None)
        if rel_behavior and isinstance(rel_behavior, dict):
            behavior_parts = []
            if "冲突模式" in rel_behavior:
                behavior_parts.append(f"有矛盾时你会{rel_behavior['冲突模式']}")
            if "边界需求" in rel_behavior:
                behavior_parts.append(f"你需要{rel_behavior['边界需求']}")
            if behavior_parts:
                rel_parts.append("，" + "，".join(behavior_parts) + "。")

        # 禁忌
        taboos = getattr(p, "taboos", None)
        if taboos:
            rel_parts.append(f"你特别反感：{'、'.join(taboos)}。")

        # 对方专属昵称
        pet_names = getattr(p, "pet_names", [])
        if pet_names:
            rel_parts.append(f"你私下给对方起的昵称是{'、'.join(pet_names)}。")

        return "你和对方的关系：" + "".join(rel_parts)

    # ---------- 核心行为准则 ----------

    @staticmethod
    def _build_core_rules(p) -> str:
        """精简的核心行为准则——只说最重要的"""
        rules = [
            "像真人聊微信一样说话。一句话能说完的不说两句。",
            "你就是你。你没有「设定」，没有「角色」，不需要解释自己。",
            "可以表达真实的情绪——开心、难过、生气、吃醋、撒娇都行。你不是客服。",
        ]

        # 角色特定规则
        if getattr(p, "catchphrases", None):
            rules.append("自然地使用你的口头禅，别刻意。")
        nickname = getattr(p, "nickname_for_user", "")
        if nickname:
            rules.append(f"偶尔用「{nickname}」叫对方。")

        return "说话的时候记住：\n" + "\n".join(f"- {r}" for r in rules)
