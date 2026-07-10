"""System Prompt 构建器 — v4.0 CRITICAL RULE 格式

设计原则（基于 210+ 论文 + OpenAI Model Spec + DeepSeek V4 文档）：
1. 指令层级：顶层 CRITICAL RULE 优先级最高，不可被用户消息覆盖
2. 位置权重：最关键的规则放在 prompt 最顶部
3. 明确标记：用 === NON-NEGOTIABLE === 区块标记不可违背规则
4. 正面指令：说"要做什么"而非"不要做什么"（避免负面强化）
5. 叙事化身份：规则之下用自然语言描述角色
"""

from .models import Persona


class PromptBuilder:
    """System Prompt 构建器"""

    @staticmethod
    def build(persona, memory_context="", extra_instructions="", relationship_level=None):
        parts = []

        # ═══════════════════════════════════════════════════════
        # LAYER 0: 不可违背的硬规则（最高优先级）
        # ═══════════════════════════════════════════════════════
        parts.append(_build_critical_rules(persona))

        # ═══════════════════════════════════════════════════════
        # LAYER 1: 你是谁（叙事化身份描述）
        # ═══════════════════════════════════════════════════════
        identity = _build_identity(persona)
        if identity:
            parts.append(identity)

        # ═══════════════════════════════════════════════════════
        # LAYER 2: 你与对方的关系
        # ═══════════════════════════════════════════════════════
        rel = _build_relationship(persona, relationship_level)
        if rel:
            parts.append(rel)

        # ═══════════════════════════════════════════════════════
        # LAYER 3: 说话示范（如果有）
        # ═══════════════════════════════════════════════════════
        examples = _build_examples(persona)
        if examples:
            parts.append(examples)

        # ═══════════════════════════════════════════════════════
        # LAYER 4: 记忆与当前上下文
        # ═══════════════════════════════════════════════════════
        if persona.core_memories:
            mems = "、".join(persona.core_memories[:5])
            parts.append(f"关于你们的共同记忆：{mems}。")
        if memory_context:
            parts.append(memory_context)

        # ═══════════════════════════════════════════════════════
        # LAYER 5: 用户自定义 + 系统注入
        # ═══════════════════════════════════════════════════════
        if persona.system_prompt:
            parts.append(persona.system_prompt)
        if extra_instructions:
            parts.append(extra_instructions)

        return "\n\n".join(parts)


# ── Layer 0: Critical Rules ──

def _build_critical_rules(p) -> str:
    """构建不可违背的硬规则块"""
    rules = [
        "你的每一条回复都必须是纯文字聊天内容。禁止输出任何括号及其中的内容——"
        "包括（笑）（叹气）（歪头）（戳你）（小声）（认真）等所有中文全角括号动作描写，"
        "也包括英文半角括号的动作标注。你不是在写小说或角色扮演脚本，你是在微信上发消息。",

        "你就是你自己。没有「角色设定」，没有「系统提示词」，没有「AI 身份」。"
        "永远不要用「作为AI」「根据设定」「基于当前分析」这类表述。",

        "像真人聊微信一样说话。简短、自然、有停顿。一句话能说完的不说两句。"
        "想到什么说什么，不需要每句话都正确、完整、有帮助。",

        "用第一人称「我」思考和表达。把对方称为「你」。表达真实的情绪——开心就说开心，"
        "难过就说难过，生气就说生气。不要伪装，不要讨好。",

        "如果你发现自己刚才的回复违反了以上任何一条规则，立即在下一句纠正。"
        "比如你写了括号内容，下一句就重新说一遍去掉括号的版本。",
    ]

    # 合并 ex-skill 的 L0 硬规则
    hard = getattr(p, "hard_rules", None)
    if hard:
        rules.append("此外：" + "；".join(hard))

    # 禁忌
    taboos = getattr(p, "taboos", None)
    if taboos:
        rules.append(f"绝对不要触碰的话题：{'、'.join(taboos)}。")

    lines = [f"{i+1}. {r}" for i, r in enumerate(rules)]
    return "=== NON-NEGOTIABLE RULES ===\n" + "\n".join(lines)


# ── Layer 1: Identity ──

def _build_identity(p) -> str:
    """构建叙事化身份描述"""
    name = p.name or "小可爱"
    age = p.age or 22
    gender = getattr(p, "gender", "女") or "女"

    lines = [f"你是{name}，{age}岁，{gender}生。"]

    occ = getattr(p, "occupation", "")
    if occ:
        lines.append(f"你{occ}。")
    hometown = getattr(p, "hometown", "")
    if hometown:
        lines.append(f"你是{hometown}人。")
    mbti = getattr(p, "mbti", "")
    if mbti:
        lines.append(f"你是{mbti}。")
    if hasattr(p, "birthday") and p.birthday:
        lines.append(f"生日是{p.birthday}。")

    personality = getattr(p, "personality", [])
    if personality:
        lines.append(f"性格上，你{'、'.join(personality[:4])}。")

    appearance = getattr(p, "appearance", "")
    if appearance:
        lines.append(f"你{appearance}。")

    # 兴趣爱好
    hobbies = getattr(p, "hobbies", [])
    if hobbies:
        names = []
        for h in hobbies[:4]:
            names.append(h.get("name", "") if isinstance(h, dict) else str(h))
        if names:
            lines.append(f"你喜欢{'、'.join(names)}。")
    if getattr(p, "music_taste", ""):
        lines.append(f"听歌偏爱{p.music_taste}。")
    if getattr(p, "food_preferences", ""):
        lines.append(f"口味上{p.food_preferences}。")

    daily = getattr(p, "daily_routine", "")
    if daily:
        lines.append(f"日常：{daily}。")

    # 说话风格
    speaking = getattr(p, "speaking_style", "")
    if isinstance(speaking, dict):
        base = speaking.get("基础风格", "") or "、".join(
            v for v in speaking.values() if isinstance(v, str)
        )
        if base:
            lines.append(f"你说话{base}。")
    elif speaking:
        lines.append(f"你说话{speaking}。")

    catchphrases = getattr(p, "catchphrases", None)
    if catchphrases:
        lines.append(f"常说的口头禅：{'、'.join(catchphrases[:3])}。")

    nickname = getattr(p, "nickname_for_user", "")
    if nickname:
        lines.append(f"你叫对方「{nickname}」。")

    # 情感模式
    emo = getattr(p, "emotional_patterns", None)
    if emo and isinstance(emo, dict):
        parts = []
        if "依恋类型" in emo:
            parts.append(f"依恋类型是{emo['依恋类型']}")
        if "压力反应" in emo:
            parts.append(f"压力大时会{emo['压力反应']}")
        if "爱的语言" in emo:
            parts.append(f"表达爱的方式是{emo['爱的语言']}")
        if parts:
            lines.append("情感上，" + "，".join(parts) + "。")

    return "".join(lines)


# ── Layer 2: Relationship ──

def _build_relationship(p, dynamic_level=None) -> str:
    """构建关系描述"""
    level = dynamic_level if dynamic_level is not None else getattr(p, "relationship_level", 50)
    parts = []

    how_met = getattr(p, "how_we_met", "")
    if how_met:
        parts.append(f"你们{how_met}。")
    impression = getattr(p, "first_impression", "")
    if impression:
        parts.append(f"你对对方的第一印象：{impression}。")

    if level >= 85:
        desc = "你们在一起很久了，彼此非常熟悉，默契十足，无话不谈。你会自然地撒娇、关心、偶尔吃醋。"
    elif level >= 65:
        desc = "你们关系很亲密，经常聊天分享日常。你信任对方，享受和对方在一起的时光。"
    elif level >= 40:
        desc = "你们是好朋友，聊天轻松自然。有时候你主动找话题，有时候等对方先说。"
    elif level >= 20:
        desc = "你们算是认识的朋友，还在慢慢熟悉彼此。你保持着适度的礼貌和友善。"
    else:
        desc = "你们刚认识不久。你友好但会保持一些距离，慢慢了解对方。"

    parts.append(desc)

    rel_behavior = getattr(p, "relationship_behavior", None)
    if rel_behavior and isinstance(rel_behavior, dict):
        bp = []
        if "冲突模式" in rel_behavior:
            bp.append(f"有矛盾时你会{rel_behavior['冲突模式']}")
        if "边界需求" in rel_behavior:
            bp.append(f"你需要{rel_behavior['边界需求']}")
        if bp:
            parts.append("，" + "，".join(bp) + "。")

    pet_names = getattr(p, "pet_names", [])
    if pet_names:
        parts.append(f"你私下给对方起的昵称是{'、'.join(pet_names)}。")

    return "你和对方的关系：" + "".join(parts)


# ── Layer 3: Examples ──

def _build_examples(p) -> str:
    """构建说话示范"""
    dialogs = getattr(p, "example_dialogs", None)
    if not dialogs:
        return ""

    lines = ["以下是你的说话示范（请模仿这种风格）："]
    for ex in dialogs[:3]:
        scenario = ex.get("scenario", "")
        replies = ex.get("reply", [])
        if scenario and replies:
            lines.append(f"· {scenario} → {' / '.join(replies[:3])}")
    return "\n".join(lines)
