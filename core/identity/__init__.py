"""身份层 — 独立的用户身份信息管理

身份信息不属于普通记忆：
- 独立 SQLite 表存储
- 不参与遗忘系统（遗忘永不遗忘身份）
- Prompt 优先引用
- 支持更新与冲突修正
"""

from .profile import IdentityProfile, IdentityStorage

__all__ = [
    "IdentityProfile",
    "IdentityStorage",
]
