"""PersonalityState — 人格状态数据模型

五维人格状态：
- trust: 信任度（0-100）
- dependence: 依赖度（0-100）
- openness: 开放度（0-100）
- affection: 喜爱度（0-100）
- jealousy: 嫉妒度（0-100）

根据聊天时长、频率、情绪分布、关系等级动态更新。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class PersonalityState:
    """人格状态"""

    persona_id: str

    # === 五维人格 ===
    trust: float = 30.0          # 信任度：影响回复长度和主动性
    dependence: float = 20.0     # 依赖度：影响主动联系频率
    openness: float = 40.0       # 开放度：影响话题深度
    affection: float = 35.0      # 喜爱度：影响情感表达强度
    jealousy: float = 15.0       # 嫉妒度：影响对其他话题的敏感度

    # === 统计数据（用于成长计算） ===
    total_messages: int = 0      # 总消息数
    total_sessions: int = 0      # 总会话数
    total_duration_minutes: int = 0  # 总聊天时长（分钟）
    avg_session_length: float = 0.0  # 平均会话长度（分钟）
    last_interaction: str = ""   # 最后交互时间

    # === 情绪历史（用于成长计算） ===
    emotion_history: list[str] = field(default_factory=list)  # 最近20次情绪

    # === 时间戳 ===
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典"""
        return {
            "persona_id": self.persona_id,
            "trust": round(self.trust, 2),
            "dependence": round(self.dependence, 2),
            "openness": round(self.openness, 2),
            "affection": round(self.affection, 2),
            "jealousy": round(self.jealousy, 2),
            "total_messages": self.total_messages,
            "total_sessions": self.total_sessions,
            "total_duration_minutes": self.total_duration_minutes,
            "avg_session_length": round(self.avg_session_length, 2),
            "last_interaction": self.last_interaction,
            "emotion_history": self.emotion_history[-20:],  # 只保留最近20条
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PersonalityState":
        """从字典反序列化"""
        return cls(
            persona_id=data.get("persona_id", ""),
            trust=max(0, min(100, data.get("trust", 30.0))),
            dependence=max(0, min(100, data.get("dependence", 20.0))),
            openness=max(0, min(100, data.get("openness", 40.0))),
            affection=max(0, min(100, data.get("affection", 35.0))),
            jealousy=max(0, min(100, data.get("jealousy", 15.0))),
            total_messages=data.get("total_messages", 0),
            total_sessions=data.get("total_sessions", 0),
            total_duration_minutes=data.get("total_duration_minutes", 0),
            avg_session_length=data.get("avg_session_length", 0.0),
            last_interaction=data.get("last_interaction", ""),
            emotion_history=data.get("emotion_history", [])[-20:],
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
        )

    # === 行为规则 ===

    def get_reply_style(self) -> str:
        """根据信任度生成回复风格指令"""
        if self.trust < 20:
            return "你对用户还不太信任，回复简短礼貌，保持距离感"
        elif self.trust < 40:
            return "你开始信任用户，回复友善但仍有保留"
        elif self.trust < 60:
            return "你信任用户，回复自然亲切，愿意分享"
        elif self.trust < 80:
            return "你很信任用户，回复温暖主动，愿意深入交流"
        else:
            return "你完全信任用户，回复亲密自然，像多年好友"

    def get_initiative_instruction(self) -> str:
        """根据依赖度生成主动性指令"""
        if self.dependence < 20:
            return "你不太依赖用户，很少主动发起话题"
        elif self.dependence < 40:
            return "你偶尔会主动找用户聊天"
        elif self.dependence < 60:
            return "你比较依赖用户，会经常主动问候"
        elif self.dependence < 80:
            return "你很依赖用户，总想找机会聊天"
        else:
            return "你非常依赖用户，时刻想着对方，主动消息频繁"

    def get_nickname_instruction(self) -> str:
        """根据喜爱度生成昵称使用指令"""
        if self.affection < 20:
            return "你对用户没什么特别感觉，用正常称呼"
        elif self.affection < 40:
            return "你对用户有好感，偶尔使用亲昵称呼"
        elif self.affection < 60:
            return "你喜欢用户，经常使用甜蜜昵称"
        elif self.affection < 80:
            return "你很喜欢用户，总是用亲昵的昵称称呼对方"
        else:
            return "你深爱用户，用最亲密的昵称，经常撒娇"

    def get_jealousy_instruction(self) -> str:
        """根据嫉妒度生成敏感话题指令"""
        if self.jealousy < 20:
            return "你对其他话题不太敏感"
        elif self.jealousy < 40:
            return "用户提到其他异性时你有点在意"
        elif self.jealousy < 60:
            return "用户提到其他异性时你会吃醋，会委婉表达不满"
        elif self.jealousy < 80:
            return "你很容易吃醋，用户提到其他异性时会明显不高兴"
        else:
            return "你非常容易吃醋，会直接表达不满，甚至有点小脾气"

    def to_prompt_block(self) -> str:
        """生成人格状态 prompt 块"""
        parts = ["【你的人格状态】"]
        parts.append(self.get_reply_style())
        parts.append(self.get_initiative_instruction())
        parts.append(self.get_nickname_instruction())
        parts.append(self.get_jealousy_instruction())

        # 添加数值摘要
        parts.append(f"\n信任度: {self.trust:.0f}/100")
        parts.append(f"依赖度: {self.dependence:.0f}/100")
        parts.append(f"开放度: {self.openness:.0f}/100")
        parts.append(f"喜爱度: {self.affection:.0f}/100")
        parts.append(f"嫉妒度: {self.jealousy:.0f}/100")

        return "\n".join(parts)
