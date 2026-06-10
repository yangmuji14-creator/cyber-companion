"""关系亲密度动态追踪器

根据对话互动动态计算用户与 AI 的亲密度 level。
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from loguru import logger


class RelationshipTracker:
    """关系亲密度追踪器

    根据对话频率、情感互动、时间衰减等因素动态计算亲密度。

    算法：
    - 基础 level 来自人设配置（默认 50）
    - 每次对话 +0.05（缓慢增长，500 次对话达到 +25）
    - 正面情感（开心/爱意/兴奋）+0.3 每次
    - 负面情感（生气/难过/焦虑）-0.2 每次
    - 3 天不聊天开始衰减，每天 -0.05
    - level 限制在 0-100 范围
    """

    # 情感分类
    POSITIVE_EMOTIONS = {"happy", "love", "excited"}
    NEGATIVE_EMOTIONS = {"angry", "sad", "anxious"}

    # 参数
    MESSAGE_BONUS = 0.05       # 每条消息的亲密度增量
    POSITIVE_BONUS = 0.3       # 正面情感增量
    NEGATIVE_PENALTY = 0.2     # 负面情感减量
    DECAY_THRESHOLD_DAYS = 3   # 开始衰减的天数
    DECAY_RATE = 0.05          # 每天衰减量
    MAX_LEVEL = 100
    MIN_LEVEL = 0

    def __init__(self, data_dir: str):
        """
        Args:
            data_dir: 数据存储目录
        """
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._file = self._data_dir / "relationships.json"
        self._data: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        """从文件加载数据"""
        if self._file.exists():
            try:
                with open(self._file, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
                logger.debug(f"Loaded relationship data for {len(self._data)} users")
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load relationship data: {e}")
                self._data = {}

    def _save(self) -> None:
        """保存数据到文件（原子写入）"""
        try:
            import tempfile
            fd, tmp_path = tempfile.mkstemp(
                dir=str(self._data_dir), suffix=".tmp"
            )
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, str(self._file))
        except Exception as e:
            logger.error(f"Failed to save relationship data: {e}")

    @staticmethod
    def _make_key(user_id: str, persona_id: str = "default") -> str:
        """构建复合存储键（用户+人设）"""
        if persona_id == "default":
            return user_id
        return f"{user_id}__{persona_id}"

    def _ensure_user(self, user_id: str, base_level: int = 50, persona_id: str = "default") -> dict[str, Any]:
        """确保用户数据存在，不存在则初始化"""
        key = self._make_key(user_id, persona_id)
        if key not in self._data:
            now = datetime.now().isoformat()
            self._data[key] = {
                "level": float(base_level),
                "message_count": 0,
                "positive_count": 0,
                "negative_count": 0,
                "last_interaction": now,
                "created_at": now,
            }
        return self._data[key]

    def get_level(self, user_id: str, base_level: int = 50, persona_id: str = "default") -> int:
        """获取用户当前亲密度（含时间衰减）

        Args:
            user_id: 用户 ID
            base_level: 人设基础亲密度
            persona_id: 人设 ID

        Returns:
            0-100 的亲密度整数值
        """
        user = self._ensure_user(user_id, base_level, persona_id)

        # 计算时间衰减
        last = datetime.fromisoformat(user["last_interaction"])
        days_idle = (datetime.now() - last).total_seconds() / 86400

        decay = 0.0
        if days_idle > self.DECAY_THRESHOLD_DAYS:
            decay = (days_idle - self.DECAY_THRESHOLD_DAYS) * self.DECAY_RATE

        level = max(self.MIN_LEVEL, min(self.MAX_LEVEL, user["level"] - decay))
        return int(round(level))

    def update(
        self,
        user_id: str,
        emotion: str = "neutral",
        base_level: int = 50,
        persona_id: str = "default",
    ) -> int:
        """更新亲密度（每次对话后调用）

        Args:
            user_id: 用户 ID
            emotion: 当前情感类型
            base_level: 人设基础亲密度
            persona_id: 人设 ID

        Returns:
            更新后的亲密度整数值
        """
        user = self._ensure_user(user_id, base_level, persona_id)
        now = datetime.now()

        # 时间衰减
        last = datetime.fromisoformat(user["last_interaction"])
        days_idle = (now - last).total_seconds() / 86400
        if days_idle > self.DECAY_THRESHOLD_DAYS:
            decay = (days_idle - self.DECAY_THRESHOLD_DAYS) * self.DECAY_RATE
            user["level"] = max(self.MIN_LEVEL, user["level"] - decay)

        # 消息计数
        user["message_count"] += 1
        user["level"] += self.MESSAGE_BONUS

        # 情感调整
        if emotion in self.POSITIVE_EMOTIONS:
            user["level"] += self.POSITIVE_BONUS
            user["positive_count"] += 1
        elif emotion in self.NEGATIVE_EMOTIONS:
            user["level"] -= self.NEGATIVE_PENALTY
            user["negative_count"] += 1

        # 限制范围
        user["level"] = max(self.MIN_LEVEL, min(self.MAX_LEVEL, user["level"]))

        # 更新时间
        user["last_interaction"] = now.isoformat()

        # 持久化
        self._save()

        return int(round(user["level"]))

    def get_stats(self, user_id: str, persona_id: str = "default") -> dict[str, Any]:
        """获取用户亲密度统计信息"""
        key = self._make_key(user_id, persona_id)
        user = self._data.get(key)
        if not user:
            return {"level": 50, "message_count": 0, "days_known": 0}
        created = datetime.fromisoformat(user["created_at"])
        days_known = (datetime.now() - created).total_seconds() / 86400
        return {
            "level": int(round(user["level"])),
            "message_count": user["message_count"],
            "positive_count": user["positive_count"],
            "negative_count": user["negative_count"],
            "days_known": round(days_known, 1),
        }

    def reset(self, user_id: str, base_level: int = 50, persona_id: str = "default") -> None:
        """重置用户亲密度"""
        key = self._make_key(user_id, persona_id)
        self._data.pop(key, None)
        self._ensure_user(user_id, base_level, persona_id)
        self._save()
