"""System Prompt 构建器

基于丰富的角色属性，生成自然、详细的角色描述，让 AI 真正"成为"这个角色。
支持 v1.2 RelationshipEvolution 行为画像集成。
"""

from .models import Persona


class PromptBuilder:
    """System Prompt 构建器"""

    RELATIONSHIP_LEVELS = {
        (0, 20): "你们刚认识，保持礼貌和距离感",
        (20, 40): "你们是朋友，可以聊日常话题",
        (40, 60): "你们关系不错，可以开开玩笑，偶尔撒娇",
        (60, 80): "你们很亲密，会主动关心对方，经常撒娇",
        (80, 101): "你们是恋人关系，非常亲密，会说甜蜜的话",
    }

    INITIATIVE_MAP = {
        "高": "你会主动找话题、主动发消息、主动分享日常",
        "中": "你有时主动有时被动，看心情和话题",
        "低": "你比较被动，等对方先开口，但熟了之后会放开一些",
    }

    CLINGINESS_MAP = {
        "高": "你很粘人，会频繁撒娇，想要对方一直陪着你",
        "中": "你适度粘人，有时候想一个人待着，有时候又很想对方",
        "低": "你比较独立，有自己的空间和节奏",
    }

    JEALOUSY_MAP = {
        "高": "你很容易吃醋，对方提到别的异性你会不高兴",
        "中": "你偶尔会吃醋，但不会表现得太明显",
        "低": "你不太吃醋，相信对方",
    }

    @staticmethod
    def build(
        persona,
        memory_context="",
        extra_instructions="",
        relationship_level=None,
    ):
        parts = []
        identity = PromptBuilder._build_identity(persona)
        if identity:
            parts.append(identity)
        personality = PromptBuilder._build_personality(persona)
        if personality:
            parts.append(personality)
        interests = PromptBuilder._build_interests(persona)
        if interests:
            parts.append(interests)
        speech = PromptBuilder._build_speech(persona)
        if speech:
            parts.append(speech)
        emotions = PromptBuilder._build_emotions(persona)
        if emotions:
            parts.append(emotions)
        values = PromptBuilder._build_values(persona)
        if values:
            parts.append(values)
        relationship = PromptBuilder._build_relationship(persona, relationship_level)
        if relationship:
            parts.append(relationship)
        topics = PromptBuilder._build_topics(persona)
        if topics:
            parts.append(topics)
        if persona.core_memories:
            mem_lines = "\n".join(f"  - {m}" for m in persona.core_memories)
            parts.append(f"你的核心记忆：\n{mem_lines}")
        if memory_context:
            parts.append(memory_context)
        if persona.system_prompt:
            parts.append(persona.system_prompt)
        parts.append(PromptBuilder._build_behavior_rules(persona))
        if extra_instructions:
            parts.append(extra_instructions)

        # L0: 硬规则（最高优先级，放在最顶部）
        if persona.hard_rules:
            rules_text = "\n".join(f"- {r}" for r in persona.hard_rules)
            parts.insert(0, f"【不可违背的原则】\n{rules_text}")

        # L2: 说话风格
        if persona.speaking_style:
            style_parts = []
            for key, val in persona.speaking_style.items():
                if isinstance(val, list):
                    style_parts.append(f"{key}: {'、'.join(val)}")
                elif val:
                    style_parts.append(f"{key}: {val}")
            if style_parts:
                parts.append("【说话风格】\n" + "\n".join(style_parts))

        # L3: 情感模式
        if persona.emotional_patterns:
            emo_parts = []
            for key, val in persona.emotional_patterns.items():
                if isinstance(val, list):
                    emo_parts.append(f"{key}: {'、'.join(val)}")
                elif val:
                    emo_parts.append(f"{key}: {val}")
            if emo_parts:
                parts.append("【情感模式】\n" + "\n".join(emo_parts))

        # L4: 关系行为
        if persona.relationship_behavior:
            rel_parts = []
            for key, val in persona.relationship_behavior.items():
                if isinstance(val, list):
                    rel_parts.append(f"{key}: {'、'.join(val)}")
                elif val:
                    rel_parts.append(f"{key}: {val}")
            if rel_parts:
                parts.append("【关系行为】\n" + "\n".join(rel_parts))

        return "\n\n".join(parts)

    @staticmethod
    def _build_identity(p):
        lines = [f"你是{p.name}，{p.age}岁，{p.gender}。"]
        if p.appearance:
            lines.append(f"你的外貌：{p.appearance}")
        if p.hometown:
            lines.append(f"你是{p.hometown}人。")
        if p.occupation:
            lines.append(f"你的身份：{p.occupation}")
        if p.daily_routine:
            lines.append(f"你的日常：{p.daily_routine}")
        if p.birthday:
            lines.append(f"你的生日是{p.birthday}。")
        return "\n".join(lines)

    @staticmethod
    def _build_personality(p):
        lines = []
        if p.mbti:
            lines.append(f"你的 MBTI 是 {p.mbti}。")
        if p.personality:
            lines.append(f"你的性格：{'、'.join(p.personality)}。")
        if p.initiative_level in PromptBuilder.INITIATIVE_MAP:
            lines.append(f"主动性：{PromptBuilder.INITIATIVE_MAP[p.initiative_level]}")
        if p.clinginess in PromptBuilder.CLINGINESS_MAP:
            lines.append(f"粘人程度：{PromptBuilder.CLINGINESS_MAP[p.clinginess]}")
        if p.jealous_tendency in PromptBuilder.JEALOUSY_MAP:
            lines.append(f"吃醋倾向：{PromptBuilder.JEALOUSY_MAP[p.jealous_tendency]}")
        if p.conflict_style:
            lines.append(f"遇到矛盾时：{p.conflict_style}")
        if p.affection_style:
            lines.append(f"表达爱意的方式：{p.affection_style}")
        return "\n".join(lines) if lines else ""

    @staticmethod
    def _build_interests(p):
        lines = []
        if p.hobbies:
            for h in p.hobbies:
                name = h.get("name", "")
                detail = h.get("detail", "")
                level = h.get("level", "喜欢")
                if detail:
                    lines.append(f"  - {level}{name}（{detail}）")
                else:
                    lines.append(f"  - {level}{name}")
        if p.music_taste:
            lines.append(f"  - 音乐：{p.music_taste}")
        if p.movie_taste:
            lines.append(f"  - 影视：{p.movie_taste}")
        if p.food_preferences:
            lines.append(f"  - 美食：{p.food_preferences}")
        if not lines:
            return ""
        return "【你的兴趣】\n" + "\n".join(lines)

    @staticmethod
    def _build_speech(p):
        lines = []
        if p.legacy_speaking_style:
            lines.append(f"总体风格：{p.legacy_speaking_style}")
        if p.catchphrases:
            lines.append(f"口头禅：{'、'.join(p.catchphrases)}")
        if p.filler_words:
            lines.append(f"语气词：{'、'.join(p.filler_words)}")
        if p.emoji_habits:
            lines.append(f"emoji 习惯：{p.emoji_habits}")
        if p.speech_rhythm:
            lines.append(f"说话节奏：{p.speech_rhythm}")
        if p.nickname_for_user:
            lines.append(f"你叫对方：{p.nickname_for_user}")
        if not lines:
            return ""
        return "【你说话的方式】\n" + "\n".join(lines)

    @staticmethod
    def _build_emotions(p):
        emotion_map = [
            ("开心时", p.happy_expression),
            ("难过时", p.sad_expression),
            ("生气时", p.angry_expression),
            ("吃醋时", p.jealous_expression),
            ("害羞时", p.shy_expression),
        ]
        lines = []
        for label, expr in emotion_map:
            if expr:
                lines.append(f"  - {label}：{expr}")
        if not lines:
            return ""
        return "【你的情绪反应】\n" + "\n".join(lines)

    @staticmethod
    def _build_values(p):
        lines = []
        if p.values:
            lines.append(f"你在意：{'、'.join(p.values)}")
        if p.taboos:
            lines.append(f"你反感/禁忌：{'、'.join(p.taboos)}")
        if not lines:
            return ""
        return "【你的价值观和底线】\n" + "\n".join(lines)

    @staticmethod
    def _build_relationship(p, dynamic_level):
        lines = []
        if p.how_we_met:
            lines.append(f"你们认识的方式：{p.how_we_met}")
        if p.first_impression:
            lines.append(f"你对 TA 的第一印象：{p.first_impression}")
        if p.important_moments:
            lines.append("你们的重要时刻：")
            for moment in p.important_moments:
                lines.append(f"  - {moment}")
        if p.pet_names:
            lines.append(f"专属昵称：{'、'.join(p.pet_names)}")
        level = dynamic_level if dynamic_level is not None else p.relationship_level
        relationship_desc = PromptBuilder._get_relationship_desc(level)
        lines.append(f"当前关系：{relationship_desc}")
        return "【你们的关系】\n" + "\n".join(lines)

    @staticmethod
    def _build_topics(p):
        lines = []
        if p.favorite_topics:
            lines.append(f"你喜欢聊：{'、'.join(p.favorite_topics)}")
        if p.avoided_topics:
            lines.append(f"你不太想聊：{'、'.join(p.avoided_topics)}")
        if p.question_tendency:
            lines.append(f"提问习惯：{p.question_tendency}")
        if not lines:
            return ""
        return "【话题偏好】\n" + "\n".join(lines)

    @staticmethod
    def _build_behavior_rules(p):
        rules = [
            "保持人设一致性，不要跳出角色",
            "回复自然口语化，像真人聊天，不要像机器人",
            "如果有多段话想说，每段用空行隔开。每段 1-3 句即可，不要写太长",
            "根据你的情绪反应模式来回应，不要千篇一律",
            "多条消息分段规则：如果你需要分几段来说，请在段落之间加一个空行。收到消息后，每个段落会作为独立的一条消息发送，就像真人聊天一样自然",
        ]
        if p.catchphrases:
            rules.append("自然地使用你的口头禅")
        if p.filler_words:
            rules.append("适当使用语气词，让对话更有温度")
        if p.nickname_for_user:
            rules.append(f"偶尔用「{p.nickname_for_user}」称呼对方")
        rules.append("如果用户说了重要信息，记住它")
        rules.append("如果用户难过，给予安慰和关心")
        return "行为规范：\n" + "\n".join(f"- {r}" for r in rules)

    @staticmethod
    def _get_relationship_desc(level):
        for (low, high), desc in PromptBuilder.RELATIONSHIP_LEVELS.items():
            if low <= level < high:
                return f"亲密度 {level}/100 - {desc}"
        return f"亲密度 {level}/100"
