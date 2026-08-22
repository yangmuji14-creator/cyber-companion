"""会话绑定 — 将 (platform, account_id, contact_id) 三元组映射到 persona。

供多账号会话隔离使用：每个外部联系人绑定一个 persona，pipeline 通过
contact_id 查询 binding 得到 persona_id，避免硬编码 DEFAULT_PERSONA_ID。
"""

from core.conversation.binding import ConversationBinding
from core.conversation.store import ConversationStore

__all__ = ["ConversationBinding", "ConversationStore"]
