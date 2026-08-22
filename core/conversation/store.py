"""ConversationStore — JSON-backed CRUD for ConversationBinding.

并发模型：threading.RLock 保护内存缓存 `_cache` 和自增计数器 `_next_id`。
所有公开方法在锁内完成读/写/持久化。RLock 可重入——`create()` 内部调用
`find()` 做去重检查时不会死锁。持久化用 `atomic_write_json`（tempfile +
os.replace），崩溃不丢数据。
"""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path

from core.config import DATA_DIR
from core.utils import atomic_write_json, read_json
from core.conversation.binding import ConversationBinding

CONVERSATIONS_FILE = DATA_DIR / "conversations.json"


class ConversationStore:
    """会话绑定存储 — 内存缓存 + JSON 持久化。"""

    def __init__(self, file_path: Path | None = None):
        self._file: Path = file_path or CONVERSATIONS_FILE
        # RLock 可重入：create() 内调 find() 时不会自死锁
        self._lock = threading.RLock()
        self._cache: list[ConversationBinding] = []
        self._next_id: int = 1
        self._load()

    # ────────── 内部 ──────────

    def _load(self) -> None:
        """启动时从 JSON 加载到内存缓存，并恢复 _next_id。"""
        data = read_json(self._file, default=None)
        if not data or "bindings" not in data:
            return
        self._cache = [ConversationBinding.from_dict(b) for b in data["bindings"]]
        # next_id = 已存在最大 conv_N 的 N + 1；无记录则 1
        max_id = 0
        for b in self._cache:
            if b.conversation_id.startswith("conv_"):
                try:
                    max_id = max(max_id, int(b.conversation_id.removeprefix("conv_")))
                except ValueError:
                    continue
        self._next_id = max_id + 1
        # 兼容旧格式 next_id 字段（取两者较大值）
        stored_next = int(data.get("next_id", 0) or 0)
        self._next_id = max(self._next_id, stored_next)

    def _save(self) -> None:
        """锁内调用：原子写 JSON。缓存已在外部更新。"""
        data = {
            "bindings": [b.to_dict() for b in self._cache],
            "next_id": self._next_id,
        }
        atomic_write_json(self._file, data)

    # ────────── 查询 ──────────

    def list(self) -> list[ConversationBinding]:
        """返回所有 binding 的浅拷贝快照。"""
        with self._lock:
            return list(self._cache)

    def get(self, conversation_id: str) -> ConversationBinding | None:
        """按 conversation_id 查找。"""
        with self._lock:
            for b in self._cache:
                if b.conversation_id == conversation_id:
                    return b
        return None

    def find(self, platform: str, account_id: str, contact_id: str) -> ConversationBinding | None:
        """按三元组查找。O(n) 遍历（binding 数 <1000，性能可接受）。"""
        with self._lock:
            for b in self._cache:
                if (b.platform == platform
                        and b.account_id == account_id
                        and b.contact_id == contact_id):
                    return b
        return None

    def list_by_platform(self, platform: str) -> list[ConversationBinding]:
        """返回某平台所有 binding（proactive messenger 用）。"""
        with self._lock:
            return [b for b in self._cache if b.platform == platform]

    # ────────── 写操作 ──────────

    def create(self, platform: str, account_id: str, contact_id: str,
               persona_id: str) -> ConversationBinding:
        """创建 binding。三元组已存在则 raise ValueError。"""
        with self._lock:
            # RLock 可重入：find() 内部 acquire 不会死锁
            existing = self.find(platform, account_id, contact_id)
            if existing:
                raise ValueError(
                    f"Conversation already exists: {existing.conversation_id}"
                )
            now = datetime.now().isoformat()
            binding = ConversationBinding(
                conversation_id=f"conv_{self._next_id}",
                platform=platform,
                account_id=account_id,
                contact_id=contact_id,
                persona_id=persona_id,
                created_at=now,
                updated_at=now,
            )
            self._cache.append(binding)
            self._next_id += 1
            self._save()
            return binding

    def update_persona(self, conversation_id: str, persona_id: str) -> ConversationBinding | None:
        """更新 binding 的 persona_id。不存在返回 None。"""
        with self._lock:
            for b in self._cache:
                if b.conversation_id == conversation_id:
                    b.persona_id = persona_id
                    b.updated_at = datetime.now().isoformat()
                    self._save()
                    return b
        return None

    def update_account_persona(
        self,
        platform: str,
        account_id: str,
        persona_id: str,
    ) -> int:
        """Synchronize every internal contact binding for one external account."""
        with self._lock:
            changed: list[tuple[ConversationBinding, str, str]] = []
            now = datetime.now().isoformat()
            for binding in self._cache:
                if binding.platform != platform or binding.account_id != account_id:
                    continue
                if binding.persona_id == persona_id:
                    continue
                changed.append((binding, binding.persona_id, binding.updated_at))
                binding.persona_id = persona_id
                binding.updated_at = now
            if not changed:
                return 0
            try:
                self._save()
            except Exception:
                for binding, old_persona, old_updated_at in changed:
                    binding.persona_id = old_persona
                    binding.updated_at = old_updated_at
                raise
            return len(changed)

    def rename(self, conversation_id: str, title: str) -> ConversationBinding | None:
        """更新 binding 的 title（用户自定义备注名）。不存在返回 None。

        传空串等于清除备注名，前端回退显示 persona name。
        """
        with self._lock:
            for b in self._cache:
                if b.conversation_id == conversation_id:
                    b.title = title
                    b.updated_at = datetime.now().isoformat()
                    self._save()
                    return b
        return None

    def delete(self, conversation_id: str) -> bool:
        """删除 binding。不存在返回 False。"""
        with self._lock:
            for i, b in enumerate(self._cache):
                if b.conversation_id == conversation_id:
                    del self._cache[i]
                    self._save()
                    return True
        return False
