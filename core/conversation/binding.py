"""ConversationBinding — 会话到 persona 的绑定记录。"""

from dataclasses import dataclass


@dataclass
class ConversationBinding:
    """一个外部联系人 ↔ persona 的绑定。

    三元组 (platform, account_id, contact_id) 唯一标识一个会话。
    conversation_id 是内部自增 ID（conv_1, conv_2, ...），用于 API 路由。
    """

    conversation_id: str   # conv_1, conv_2, ...
    platform: str          # "wechat" | "web" | "cli" | "api"
    account_id: str        # wechat account_id, "" for non-wechat
    contact_id: str        # wxid for wechat, persona_id for web
    persona_id: str        # 绑定的 persona_id
    created_at: str = ""   # ISO datetime
    updated_at: str = ""   # ISO datetime
    title: str = ""        # 用户自定义备注名；空则前端显示 persona name

    @classmethod
    def from_dict(cls, d: dict) -> "ConversationBinding":
        """从 dict 反序列化，缺失字段用默认值（向后兼容旧数据）。"""
        return cls(
            conversation_id=d.get("conversation_id", ""),
            platform=d.get("platform", ""),
            account_id=d.get("account_id", ""),
            contact_id=d.get("contact_id", ""),
            persona_id=d.get("persona_id", ""),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
            title=d.get("title", ""),
        )

    def to_dict(self) -> dict:
        """序列化为 dict（写盘格式）。"""
        return {
            "conversation_id": self.conversation_id,
            "platform": self.platform,
            "account_id": self.account_id,
            "contact_id": self.contact_id,
            "persona_id": self.persona_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "title": self.title,
        }
